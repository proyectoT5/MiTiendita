from __future__ import absolute_import, unicode_literals

import re

from django.db.models.sql import compiler

# query_class returns the base class to use for Django queries.
# The custom 'SqlServerQuery' class derives from django.db.models.sql.query.Query
# which is passed in as "QueryClass" by Django itself.
#
# SqlServerQuery overrides:
# ...insert queries to add "SET IDENTITY_INSERT" if needed.
# ...select queries to emulate LIMIT/OFFSET for sliced queries.

# Pattern to scan a column data type string and split the data type from any
# constraints or other included parts of a column definition. Based upon
# <column_definition> from http://msdn.microsoft.com/en-us/library/ms174979.aspx
_re_data_type_terminator = re.compile(
    r'\s*\b(?:' +
    r'filestream|collate|sparse|not|null|constraint|default|identity|rowguidcol' +
    r'|primary|unique|clustered|nonclustered|with|on|foreign|references|check' +
    ')',
    re.IGNORECASE,
)


_re_constant = re.compile(r'\s*\(?\s*\d+\s*\)?\s*')


class SQLCompiler(compiler.SQLCompiler):

    def as_sql(self, with_limits=True, with_col_aliases=False, subquery=False):
        # Get out of the way if we're not a select query or there's no limiting involved.
        has_limit_offset = with_limits and (self.query.low_mark or self.query.high_mark is not None)
        try:
            if not has_limit_offset:
                # The ORDER BY clause is invalid in views, inline functions,
                # derived tables, subqueries, and common table expressions,
                # unless TOP or FOR XML is also specified.
                setattr(self.query, '_mssql_ordering_not_allowed', with_col_aliases)

            # let the base do its thing, but we'll handle limit/offset
            sql, fields = super(SQLCompiler, self).as_sql(
                with_limits=False,
                with_col_aliases=with_col_aliases,
                subquery=subquery,
            )

            if has_limit_offset:
                if ' order by ' not in sql.lower():
                    # Must have an ORDER BY to slice using OFFSET/FETCH. If
                    # there is none, use the first column, which is typically a
                    # PK
                    sql += ' ORDER BY 1'
                sql += ' OFFSET %d ROWS' % (self.query.low_mark or 0)
                if self.query.high_mark is not None:
                    sql += ' FETCH NEXT %d ROWS ONLY' % (self.query.high_mark - self.query.low_mark)
        finally:
            if not has_limit_offset:
                # remove in case query is ever reused
                delattr(self.query, '_mssql_ordering_not_allowed')

        return sql, fields

    def get_ordering(self):
        # The ORDER BY clause is invalid in views, inline functions,
        # derived tables, subqueries, and common table expressions,
        # unless TOP or FOR XML is also specified.
        if getattr(self.query, '_mssql_ordering_not_allowed', False):
            return (None, [], [])
        return super(SQLCompiler, self).get_ordering()

    def collapse_group_by(self, expressions, having):
        expressions = super(SQLCompiler, self).collapse_group_by(expressions, having)
        # MSSQL doesn't support having constants in the GROUP BY clause. Django
        # does this for exists() queries that have GROUP BY.
        return [x for x in expressions if not _re_constant.match(getattr(x, 'sql', ''))]


class SQLInsertCompiler(compiler.SQLInsertCompiler, SQLCompiler):
    # search for after table/column list
    _re_values_sub = re.compile(
        r'(?P<prefix>\)|\])(?P<default>\s*|\s*default\s*)values(?P<suffix>\s*|\s+\()?',
        re.IGNORECASE
    )
    # ... and insert the OUTPUT clause between it and the values list (or DEFAULT VALUES).
    _values_repl = r'\g<prefix> OUTPUT INSERTED.{col} INTO @sqlserver_ado_return_id\g<default>VALUES\g<suffix>'

    def as_sql(self, *args, **kwargs):
        # Fix for Django ticket #14019
        if not hasattr(self, 'return_id'):
            self.return_id = False

        result = super(SQLInsertCompiler, self).as_sql(*args, **kwargs)
        return [self._fix_insert(x[0], x[1]) for x in result]

    def _fix_insert(self, sql, params):
        """
        Wrap the passed SQL with IDENTITY_INSERT statements and apply
        other necessary fixes.
        """
        meta = self.query.get_meta()

        if meta.has_auto_field:
            if hasattr(self.query, 'fields'):
                # django 1.4 replaced columns with fields
                fields = self.query.fields
                auto_field = meta.auto_field
            else:
                # < django 1.4
                fields = self.query.columns
                auto_field = meta.auto_field.db_column or meta.auto_field.column

            auto_in_fields = auto_field in fields

            quoted_table = self.connection.ops.quote_name(meta.db_table)
            if not fields or (auto_in_fields and len(fields) == 1 and not params):
                # convert format when inserting only the primary key without
                # specifying a value
                sql = 'INSERT INTO {0} DEFAULT VALUES'.format(
                    quoted_table
                )
                params = []
            elif auto_in_fields:
                # wrap with identity insert
                sql = 'SET IDENTITY_INSERT {table} ON;{sql};SET IDENTITY_INSERT {table} OFF'.format(
                    table=quoted_table,
                    sql=sql,
                )

        # mangle SQL to return ID from insert
        # http://msdn.microsoft.com/en-us/library/ms177564.aspx
        if self.return_id and self.connection.features.can_return_id_from_insert:
            col = self.connection.ops.quote_name(meta.pk.db_column or meta.pk.get_attname())

            # Determine datatype for use with the table variable that will return the inserted ID
            pk_db_type = _re_data_type_terminator.split(meta.pk.db_type(self.connection))[0]

            # NOCOUNT ON to prevent additional trigger/stored proc related resultsets
            sql = 'SET NOCOUNT ON;{declare_table_var};{sql};{select_return_id}'.format(
                sql=sql,
                declare_table_var="DECLARE @sqlserver_ado_return_id table ({col_name} {pk_type})".format(
                    col_name=col,
                    pk_type=pk_db_type,
                ),
                select_return_id="SELECT * FROM @sqlserver_ado_return_id",
            )

            output = self._values_repl.format(col=col)
            sql = self._re_values_sub.sub(output, sql)

        return sql, params


class SQLDeleteCompiler(compiler.SQLDeleteCompiler, SQLCompiler):
    pass


class SQLUpdateCompiler(compiler.SQLUpdateCompiler, SQLCompiler):
    def as_sql(self):
        sql, params = super(SQLUpdateCompiler, self).as_sql()
        if sql:
            # Need the NOCOUNT OFF so UPDATE returns a count, instead of -1
            sql = 'SET NOCOUNT OFF; {0}; SET NOCOUNT ON'.format(sql)
        return sql, params


class SQLAggregateCompiler(compiler.SQLAggregateCompiler, SQLCompiler):
    pass
