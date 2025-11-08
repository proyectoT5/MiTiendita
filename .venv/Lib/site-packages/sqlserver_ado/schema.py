import binascii
import datetime
from logging import getLogger
from django.db.backends.utils import truncate_name
from django.db.models.fields import AutoField
from django.db.models.fields.related import ManyToManyField
from django.db.utils import NotSupportedError
from django.utils import six
from django.utils.text import force_text

from django.db.backends.base.schema import BaseDatabaseSchemaEditor

logger = getLogger('django.db.backends.schema')


def _related_non_m2m_objects(old_field, new_field):
    # Filters out m2m objects from reverse relations.
    # Returns (old_relation, new_relation) tuples.
    return zip(
        (obj for obj in old_field.model._meta.related_objects if not obj.field.many_to_many),
        (obj for obj in new_field.model._meta.related_objects if not obj.field.many_to_many)
    )


class DatabaseSchemaEditor(BaseDatabaseSchemaEditor):
    sql_rename_table = "sp_rename '%(old_table)s', '%(new_table)s'"
    sql_delete_table = "DROP TABLE %(table)s"

    sql_create_column = "ALTER TABLE %(table)s ADD %(column)s %(definition)s"
    sql_alter_column_type = "ALTER COLUMN %(column)s %(type)s"
    sql_alter_column_null = "ALTER COLUMN %(column)s %(type)s NULL"
    sql_alter_column_not_null = "ALTER COLUMN %(column)s %(type)s NOT NULL"
    sql_alter_column_default = "ADD CONSTRAINT %(constraint_name)s DEFAULT %(default)s FOR %(column)s"
    sql_alter_column_no_default = "ALTER COLUMN %(column)s DROP CONSTRAINT %(constraint_name)s"
    sql_delete_column = "ALTER TABLE %(table)s DROP COLUMN %(column)s"
    sql_rename_column = "sp_rename '%(table)s.%(old_column)s', '%(new_column)s', 'COLUMN'"

    sql_create_fk = "ALTER TABLE %(table)s ADD CONSTRAINT %(name)s" \
                    " FOREIGN KEY (%(column)s) REFERENCES %(to_table)s (%(to_column)s)"

    sql_delete_index = "DROP INDEX %(name)s ON %(table)s"

    _sql_drop_inbound_foreign_keys = '''
DECLARE @sql nvarchar(max)
WHILE 1=1
BEGIN
    SELECT TOP 1
        @sql = N'ALTER TABLE [' + OBJECT_SCHEMA_NAME(parent_object_id) + N'].[' +
        OBJECT_NAME(parent_object_id) +'] DROP CONSTRAINT [' + name + N']'
    FROM sys.foreign_keys
    WHERE referenced_object_id = object_id(%s)
    IF @@ROWCOUNT = 0 BREAK
    EXEC (@sql)
END'''

    _sql_drop_primary_key = '''
DECLARE @sql nvarchar(max)
WHILE 1=1
BEGIN
    SELECT TOP 1
        @sql = N'ALTER TABLE [' + CONSTRAINT_SCHEMA + N'].[' + TABLE_NAME +
        N'] DROP CONSTRAINT [' + CONSTRAINT_NAME+ N']'
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu ON tc.CONSTRAINT_NAME = ccu.Constraint_name
    WHERE CONSTRAINT_TYPE = 'PRIMARY KEY' AND TABLE_NAME LIKE %s AND COLUMN_NAME = %s
    IF @@ROWCOUNT = 0 BREAK
    EXEC (@sql)
END'''

    # Map provides a concise prefix for constraints of the same type
    constraint_type_prefix_map = {
        'UNIQUE': 'UX_',
        'INDEX': 'IX_',
        'DEFAULT': 'DF_',
        'CHECK': 'CK_',
        'PK': 'PK_',
        'FK': 'FK_',
        '': '',
    }

    def _create_constraint_name(self, model, column_names, constraint_type='', suffix=""):
        """
        Generates a unique name for a constraint.
        """
        column = '_'.join(column_names) if isinstance(column_names, (list, tuple)) else column_names
        name = '%s%s_%s%s' % (
            self.constraint_type_prefix_map.get(constraint_type.upper(), ''),
            model._meta.db_table,
            column,
            suffix,
        )
        return truncate_name(name, length=self.connection.ops.max_name_length(), hash_len=8)

    def alter_db_table(self, model, old_db_table, new_db_table):
        # sp_rename requires that objects not be quoted because they are string literals
        self.execute(self.sql_rename_table % {
            "old_table": old_db_table,
            "new_table": new_db_table,
        })

    def delete_model(self, model):
        # Drop all inbound FKs before dropping table
        self.execute(self._sql_drop_inbound_foreign_keys, [model._meta.db_table])
        super(DatabaseSchemaEditor, self).delete_model(model)

    def delete_db_column(self, model, column):
        # drop all of the column constraints to avoid the database blocking the column removal
        with self.connection.cursor() as cursor:
            constraints = self.connection.introspection.get_constraints(cursor, model._meta.db_table)
            for name, constraint in six.iteritems(constraints):
                if column in constraint['columns']:
                    sql = 'ALTER TABLE %(table)s DROP CONSTRAINT [%(constraint)s]' % {
                        'table': model._meta.db_table,
                        'constraint': name,
                    }
                    cursor.execute(sql)
        super(DatabaseSchemaEditor, self).delete_db_column(model, column)

    def remove_field(self, model, field):
        """
        Removes a field from a model. Usually involves deleting a column,
        but for M2Ms may involve deleting a table.
        """
        # Special-case implicit M2M tables
        if isinstance(field, ManyToManyField) and field.rel.through._meta.auto_created:
            return self.delete_model(field.rel.through)
        # It might not actually have a column behind it
        if field.db_parameters(connection=self.connection)['type'] is None:
            return
        # Drop all constraints
        constraint_types = [
            (self.sql_delete_fk, {'foreign_key': True}),
            (self.sql_delete_pk, {'primary_key': True}),
            (self.sql_delete_index, {'index': True}),
            (self.sql_delete_unique, {'unique': True}),
            (self.sql_delete_check, {'check': True}),
        ]
        for template, kwargs in constraint_types:
            names = self._constraint_names(model, [field.column], **kwargs)
            for name in names:
                self.execute(self._delete_constraint_sql(template, model, name))
        # Delete the column
        sql = self.sql_delete_column % {
            "table": self.quote_name(model._meta.db_table),
            "column": self.quote_name(field.column),
        }
        self.execute(sql)
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def _alter_field(self, model, old_field, new_field, old_type, new_type,
                     old_db_params, new_db_params, strict=False):
        """Actually perform a "physical" (non-ManyToMany) field update."""

        # Has changed to AutoField
        if not isinstance(old_field, AutoField) and isinstance(new_field, AutoField):
            raise NotSupportedError('Cannot alter a non-AutoField to an AutoField')

        # Drop any FK constraints, we'll remake them later
        fks_dropped = set()
        if old_field.rel and old_field.db_constraint:
            fk_names = self._constraint_names(model, [old_field.column], foreign_key=True)
            if strict and len(fk_names) != 1:
                raise ValueError("Found wrong number (%s) of foreign key constraints for %s.%s" % (
                    len(fk_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for fk_name in fk_names:
                fks_dropped.add((old_field.column,))
                self.execute(self._delete_constraint_sql(self.sql_delete_fk, model, fk_name))
        # Has unique been removed?
        if old_field.unique and (not new_field.unique or (not old_field.primary_key and new_field.primary_key)):
            # Find the unique constraint for this field
            constraint_names = self._constraint_names(model, [old_field.column], unique=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of unique constraints for %s.%s" % (
                    len(constraint_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for constraint_name in constraint_names:
                self.execute(self._delete_constraint_sql(self.sql_delete_unique, model, constraint_name))
        # Drop incoming FK constraints if we're a primary key and things are going
        # to change.
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            # '_meta.related_field' also contains M2M reverse fields, these
            # will be filtered out
            for _old_rel, new_rel in _related_non_m2m_objects(old_field, new_field):
                rel_fk_names = self._constraint_names(
                    new_rel.related_model, [new_rel.field.column], foreign_key=True
                )
                for fk_name in rel_fk_names:
                    self.execute(self._delete_constraint_sql(self.sql_delete_fk, new_rel.related_model, fk_name))
        # Removed an index? (no strict check, as multiple indexes are possible)
        if (old_field.db_index and not new_field.db_index and
                not old_field.unique and not
                (not new_field.unique and old_field.unique)):
            # Find the index for this field
            index_names = self._constraint_names(model, [old_field.column], index=True)
            for index_name in index_names:
                self.execute(self._delete_constraint_sql(self.sql_delete_index, model, index_name))
        # Change check constraints?
        if old_db_params['check'] != new_db_params['check'] and old_db_params['check']:
            constraint_names = self._constraint_names(model, [old_field.column], check=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of check constraints for %s.%s" % (
                    len(constraint_names),
                    model._meta.db_table,
                    old_field.column,
                ))
            for constraint_name in constraint_names:
                self.execute(self._delete_constraint_sql(self.sql_delete_check, model, constraint_name))
        # Have they renamed the column?
        if old_field.column != new_field.column:
            self.execute(self._rename_field_sql(model._meta.db_table, old_field, new_field, new_type))
        # Next, start accumulating actions to do
        actions = []
        null_actions = []
        post_actions = []
        # Type change?
        if old_type != new_type:
            fragment, other_actions = self._alter_column_type_sql(
                model._meta.db_table, old_field, new_field, new_type
            )
            actions.append(fragment)
            post_actions.extend(other_actions)
        # When changing a column NULL constraint to NOT NULL with a given
        # default value, we need to perform 4 steps:
        #  1. Add a default for new incoming writes
        #  2. Update existing NULL rows with new default
        #  3. Replace NULL constraint with NOT NULL
        #  4. Drop the default again.
        # Default change?
        old_default = self.effective_default(old_field)
        new_default = self.effective_default(new_field)
        needs_database_default = (
            old_default != new_default and
            new_default is not None and
            not self.skip_default(new_field)
        )
        if needs_database_default:
            constraint_name = self._create_constraint_name(model, new_field.column, constraint_type='default')
            if self.connection.features.requires_literal_defaults:
                # Some databases can't take defaults as a parameter (oracle)
                # If this is the case, the individual schema backend should
                # implement prepare_default
                actions.append((
                    self.sql_alter_column_default % {
                        "column": self.quote_name(new_field.column),
                        "default": self.prepare_default(new_default),
                        "constraint_name": constraint_name,
                    },
                    [],
                ))
            else:
                actions.append((
                    self.sql_alter_column_default % {
                        "column": self.quote_name(new_field.column),
                        "default": "%s",
                        "constraint_name": constraint_name,
                    },
                    [new_default],
                ))
        # Nullability change?
        if old_field.null != new_field.null or old_type != new_type:
            if (self.connection.features.interprets_empty_strings_as_nulls and
                    new_field.get_internal_type() in ("CharField", "TextField")):
                # The field is nullable in the database anyway, leave it alone
                pass
            elif new_field.null:
                null_actions.append((
                    self.sql_alter_column_null % {
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    },
                    [],
                ))
            else:
                null_actions.append((
                    self.sql_alter_column_not_null % {
                        "column": self.quote_name(new_field.column),
                        "type": new_type,
                    },
                    [],
                ))
        # Only if we have a default and there is a change from NULL to NOT NULL
        four_way_default_alteration = (
            new_field.has_default() and
            (old_field.null and not new_field.null)
        )
        if actions or null_actions:
            if not four_way_default_alteration:
                # If we don't have to do a 4-way default alteration we can
                # directly run a (NOT) NULL alteration
                actions = actions + null_actions
            # Combine actions together if we can (e.g. postgres)
            if self.connection.features.supports_combined_alters and actions:
                sql, params = tuple(zip(*actions))
                actions = [(", ".join(sql), sum(params, []))]
            # Apply those actions
            for sql, params in actions:
                self.execute(
                    self.sql_alter_column % {
                        "table": self.quote_name(model._meta.db_table),
                        "changes": sql,
                    },
                    params,
                )
            if four_way_default_alteration:
                # Update existing rows with default value
                self.execute(
                    self.sql_update_with_default % {
                        "table": self.quote_name(model._meta.db_table),
                        "column": self.quote_name(new_field.column),
                        "default": "%s",
                    },
                    [new_default],
                )
                # Since we didn't run a NOT NULL change before we need to do it
                # now
                for sql, params in null_actions:
                    self.execute(
                        self.sql_alter_column % {
                            "table": self.quote_name(model._meta.db_table),
                            "changes": sql,
                        },
                        params,
                    )
        if post_actions:
            for sql, params in post_actions:
                self.execute(sql, params)
        # Added a unique?
        if (not old_field.unique and new_field.unique) or (
            old_field.primary_key and not new_field.primary_key and new_field.unique
        ):
            self.execute(self._create_unique_sql(model, [new_field.column]))
        # Added an index?
        if (not old_field.db_index and new_field.db_index and
                not new_field.unique and not
                (not old_field.unique and new_field.unique)):
            self.execute(self._create_index_sql(model, [new_field], suffix="_uniq"))
        # Type alteration on primary key? Then we need to alter the column
        # referring to us.
        rels_to_update = []
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            rels_to_update.extend(_related_non_m2m_objects(old_field, new_field))
        # Changed to become primary key?
        # Note that we don't detect unsetting of a PK, as we assume another field
        # will always come along and replace it.
        if not old_field.primary_key and new_field.primary_key:
            # First, drop the old PK
            constraint_names = self._constraint_names(model, primary_key=True)
            if strict and len(constraint_names) != 1:
                raise ValueError("Found wrong number (%s) of PK constraints for %s" % (
                    len(constraint_names),
                    model._meta.db_table,
                ))
            for constraint_name in constraint_names:
                self.execute(self._delete_constraint_sql(self.sql_delete_pk, model, constraint_name))
            # Make the new one
            self.execute(
                self.sql_create_pk % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self.quote_name(self._create_index_name(model, [new_field.column], suffix="_pk")),
                    "columns": self.quote_name(new_field.column),
                }
            )
            # Update all referencing columns
            rels_to_update.extend(_related_non_m2m_objects(old_field, new_field))
        # Handle our type alters on the other end of rels from the PK stuff above
        for old_rel, new_rel in rels_to_update:
            rel_db_params = new_rel.field.db_parameters(connection=self.connection)
            rel_type = rel_db_params['type']
            fragment, other_actions = self._alter_column_type_sql(
                new_rel.related_model._meta.db_table, old_rel.field, new_rel.field, rel_type
            )
            self.execute(
                self.sql_alter_column % {
                    "table": self.quote_name(new_rel.related_model._meta.db_table),
                    "changes": fragment[0],
                },
                fragment[1],
            )
            for sql, params in other_actions:
                self.execute(sql, params)
        # Does it have a foreign key?
        if (new_field.rel and
                (fks_dropped or not old_field.rel or not old_field.db_constraint) and
                new_field.db_constraint):
            self.execute(self._create_fk_sql(model, new_field, "_fk_%(to_table)s_%(to_column)s"))
        # Rebuild FKs that pointed to us if we previously had to drop them
        if old_field.primary_key and new_field.primary_key and old_type != new_type:
            for rel in new_field.model._meta.related_objects:
                if not rel.many_to_many:
                    self.execute(self._create_fk_sql(rel.related_model, rel.field, "_fk"))
        # Does it have check constraints we need to add?
        if old_db_params['check'] != new_db_params['check'] and new_db_params['check']:
            self.execute(
                self.sql_create_check % {
                    "table": self.quote_name(model._meta.db_table),
                    "name": self.quote_name(self._create_index_name(model, [new_field.column], suffix="_check")),
                    "column": self.quote_name(new_field.column),
                    "check": new_db_params['check'],
                }
            )
        # Drop the default if we need to
        # (Django usually does not use in-database defaults)
        if needs_database_default:
            sql, params = self._drop_default_column(model, new_field.column)
            self.execute(sql, params)

        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def add_field(self, model, field):
        """
        Creates a field on a model.
        Usually involves adding a column, but may involve adding a
        table instead (for M2M fields)
        """
        # Special-case implicit M2M tables
        if isinstance(field, ManyToManyField) and field.rel.through._meta.auto_created:
            return self.create_model(field.rel.through)
        # Get the column's definition
        definition, params = self.column_sql(model, field, include_default=True)
        # It might not actually have a column behind it
        if definition is None:
            return
        # Check constraints can go on the column SQL here
        db_params = field.db_parameters(connection=self.connection)
        if db_params['check']:
            definition += " CHECK (%s)" % db_params['check']
        # Build the SQL and run it
        sql = self.sql_create_column % {
            "table": self.quote_name(model._meta.db_table),
            "column": self.quote_name(field.column),
            "definition": definition,
        }
        self.execute(sql, params)
        # Drop the default if we need to
        # (Django usually does not use in-database defaults)
        if not self.skip_default(field) and field.default is not None:
            sql, params = self._drop_default_column(model, field.column)
            self.execute(sql, params)
        # Add an index, if required
        if field.db_index and not field.unique:
            self.deferred_sql.append(self._create_index_sql(model, [field]))
        # Add any FK constraints later
        if field.rel and self.connection.features.supports_foreign_keys and field.db_constraint:
            self.deferred_sql.append(self._create_fk_sql(model, field, "_fk_%(to_table)s_%(to_column)s"))
        # Reset connection if required
        if self.connection.features.connection_persists_old_columns:
            self.connection.close()

    def _rename_field_sql(self, table, old_field, new_field, new_type):
        return self.sql_rename_column % {
            "table": self.quote_name(table),
            "old_column": self.quote_name(old_field.column),
            "new_column": new_field.column,  # not quoting because it's a string literal
            "type": new_type,
        }

    def _drop_default_column(self, model, column):
        """
        Drop the default constraint for a column on a model.
        """
        sql = '''
DECLARE @sql nvarchar(max)
WHILE 1=1
BEGIN
    SELECT TOP 1 @sql = N'ALTER TABLE %(table)s DROP CONSTRAINT [' + dc.NAME + N']'
    FROM sys.default_constraints dc
    JOIN sys.columns c
        ON c.default_object_id = dc.object_id
    WHERE
        dc.parent_object_id = OBJECT_ID(%%s)
    AND c.name = %%s
    IF @@ROWCOUNT = 0 BREAK
    EXEC (@sql)
END''' % {'table': model._meta.db_table}
        params = [model._meta.db_table, column]
        return sql, params

    def prepare_default(self, value):
        return self.quote_value(value)

    def quote_value(self, value):
        if isinstance(value, (datetime.date, datetime.time, datetime.datetime)):
            return "'%s'" % value
        elif isinstance(value, six.string_types):
            return "'%s'" % six.text_type(value).replace("\'", "\'\'")
        elif isinstance(value, six.buffer_types):
            return '0x%s' % force_text(binascii.hexlify(value))
        elif isinstance(value, bool):
            return "1" if value else "0"
        elif value is None:
            return "NULL"
        else:
            return str(value)

    # def execute(self, sql, params=[]):
    #     """
    #     Executes the given SQL statement, with optional parameters.
    #     """
    #     # Log the command we're running, then run it
    #     logger.debug("%s; (params %r)" % (sql, params))
    #     if self.collect_sql:
    #         ending = "" if sql.endswith(";") else ";"
    #         if params is not None:
    #             self.collected_sql.append((sql % tuple(map(self.quote_value, params))) + ending)
    #         else:
    #             self.collected_sql.append(sql + ending)
    #     else:
    #         print('sql=', sql)
    #         print('    params=', params)
    #         with self.connection.cursor() as cursor:
    #             cursor.execute(sql, params)
