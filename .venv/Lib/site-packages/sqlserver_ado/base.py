"""Microsoft SQL Server database backend for Django."""
from __future__ import absolute_import, unicode_literals

import warnings

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_ipv46_address as ip_validator
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.backends.base.client import BaseDatabaseClient
from django.db.backends.base.validation import BaseDatabaseValidation
from django.db.utils import IntegrityError

from . import dbapi as Database

from .introspection import DatabaseIntrospection
from .creation import DatabaseCreation
from .features import DatabaseFeatures
from .operations import DatabaseOperations
from .schema import DatabaseSchemaEditor


def is_ip_address(value):
    """
    Returns True if value is a valid IP address, otherwise False.
    """
    try:
        ip_validator(value)
    except ValidationError:
        return False
    return True


def connection_string_from_settings():
    from django.conf import settings
    db_settings = getattr(settings, 'DATABASES', {}).get('default', None)
    return make_connection_string(db_settings)


def make_connection_string(settings):
    db_name = settings['NAME'].strip()
    db_host = settings['HOST'] or '127.0.0.1'
    db_port = settings['PORT']
    db_user = settings['USER']
    db_password = settings['PASSWORD']
    options = settings.get('OPTIONS', {})

    if len(db_name) == 0:
        raise ImproperlyConfigured("You need to specify a DATABASE NAME in your Django settings file.")

    # Connection strings courtesy of:
    # http://www.connectionstrings.com/?carrier=sqlserver

    # If a port is given, force a TCP/IP connection. The host should be an IP address in this case.
    if db_port:
        if not is_ip_address(db_host):
            raise ImproperlyConfigured("When using DATABASE PORT, DATABASE HOST must be an IP address.")
        try:
            db_port = int(db_port)
        except ValueError:
            raise ImproperlyConfigured("DATABASE PORT must be a number.")
        db_host = '{0},{1};Network Library=DBMSSOCN'.format(db_host, db_port)

    # If no user is specified, use integrated security.
    if db_user != '':
        auth_string = 'UID={0};PWD={1}'.format(db_user, db_password)
    else:
        auth_string = 'Integrated Security=SSPI'

    parts = [
        'DATA SOURCE={0};Initial Catalog={1}'.format(db_host, db_name),
        auth_string
    ]

    if not options.get('provider', None):
        options['provider'] = 'sqlncli10'

    parts.append('PROVIDER={0}'.format(options['provider']))

    extra_params = options.get('extra_params', '')

    if 'sqlncli' in options['provider'].lower() and 'datatypecompatibility=' not in extra_params.lower():
        # native client needs a compatibility mode that behaves like OLEDB
        parts.append('DataTypeCompatibility=80')

    if options.get('use_mars', True) and 'mars connection=' not in extra_params.lower():
        parts.append('MARS Connection=True')

    if extra_params:
        parts.append(options['extra_params'])

    return ";".join(parts)


VERSION_SQL2012 = 11


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'microsoft'

    Database = Database
    SchemaEditorClass = DatabaseSchemaEditor

    operators = {
        "exact": "= %s",
        "iexact": "LIKE %s ESCAPE '\\'",
        "contains": "LIKE %s ESCAPE '\\'",
        "icontains": "LIKE %s ESCAPE '\\'",
        "gt": "> %s",
        "gte": ">= %s",
        "lt": "< %s",
        "lte": "<= %s",
        "startswith": "LIKE %s ESCAPE '\\'",
        "endswith": "LIKE %s ESCAPE '\\'",
        "istartswith": "LIKE %s ESCAPE '\\'",
        "iendswith": "LIKE %s ESCAPE '\\'",
    }

    # The patterns below are used to generate SQL pattern lookup clauses when
    # the right-hand side of the lookup isn't a raw string (it might be an expression
    # or the result of a bilateral transformation).
    # In those cases, special characters for LIKE operators (e.g. \, *, _) should be
    # escaped on database side.
    #
    # Note: we use str.format() here for readability as '%' is used as a wildcard for
    # the LIKE operator.
    pattern_esc = r"REPLACE(REPLACE(REPLACE({}, '\', '\\'), '%%', '\%%'), '_', '\_')"
    pattern_ops = {
        'contains': r"LIKE CONCAT('%%', {}, '%%') ESCAPE '\'",
        'icontains': r"LIKE CONCAT('%%', {}, '%%') ESCAPE '\'",
        'startswith': r"LIKE CONCAT({}, '%%') ESCAPE '\'",
        'istartswith': r"LIKE CONCAT({}, '%%') ESCAPE '\'",
        'endswith': r"LIKE CONCAT('%%', {}) ESCAPE '\'",
        'iendswith': r"LIKE CONCAT('%%', {}) ESCAPE '\'",
    }

    # This dictionary maps Field objects to their associated Server Server column
    # types, as strings. Column-type strings can contain format strings; they'll
    # be interpolated against the values of Field.__dict__.
    data_types = {
        'AutoField':                    'int IDENTITY (1, 1)',
        'BigAutoField':                 'bigint IDENTITY (1, 1)',
        'BigIntegerField':              'bigint',
        'BinaryField':                  'varbinary(max)',
        'BooleanField':                 'bit',
        'CharField':                    'nvarchar(%(max_length)s)',
        'CommaSeparatedIntegerField':   'nvarchar(%(max_length)s)',
        'DateField':                    'date',
        'DateTimeField':                'datetime2',
        'DateTimeOffsetField':          'datetimeoffset',
        'DecimalField':                 'decimal(%(max_digits)s, %(decimal_places)s)',
        'DurationField':                'bigint',
        'FileField':                    'nvarchar(%(max_length)s)',
        'FilePathField':                'nvarchar(%(max_length)s)',
        'FloatField':                   'double precision',
        'GenericIPAddressField':        'nvarchar(39)',
        'IntegerField':                 'int',
        'IPAddressField':               'nvarchar(15)',
        'LegacyDateField':              'datetime',
        'LegacyDateTimeField':          'datetime',
        'LegacyTimeField':              'time',
        'NewDateField':                 'date',
        'NewDateTimeField':             'datetime2',
        'NewTimeField':                 'time',
        'NullBooleanField':             'bit',
        'OneToOneField':                'int',
        'PositiveIntegerField':         'int',
        'PositiveSmallIntegerField':    'smallint',
        'SlugField':                    'nvarchar(%(max_length)s)',
        'SmallIntegerField':            'smallint',
        'TextField':                    'nvarchar(max)',
        'TimeField':                    'time',
        'URLField':                     'nvarchar(%(max_length)s)',
        'UUIDField':                    'uniqueidentifier',
    }

    data_type_check_constraints = {
        'PositiveIntegerField': '%(qn_column)s >= 0',
        'PositiveSmallIntegerField': '%(qn_column)s >= 0',
    }

    def __init__(self, *args, **kwargs):
        self.use_transactions = kwargs.pop('use_transactions', None)

        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        try:
            self.command_timeout = int(self.settings_dict.get('COMMAND_TIMEOUT', 30))
        except ValueError:
            self.command_timeout = 30

        options = self.settings_dict.get('OPTIONS', {})
        try:
            self.cast_avg_to_float = not bool(options.get('disable_avg_cast', False))
        except ValueError:
            self.cast_avg_to_float = False

        if 'use_legacy_date_fields' in options:
            warnings.warn(
                "The `use_legacy_date_fields` setting is no longer supported. "
                "If you need to use the legacy SQL 'datetime' datatype, "
                "you must replace them with the provided model fields.",
                DeprecationWarning)

        self.features = DatabaseFeatures(self)
        self.ops = DatabaseOperations(self)
        self.client = BaseDatabaseClient(self)
        self.creation = DatabaseCreation(self)
        self.introspection = DatabaseIntrospection(self)
        self.validation = BaseDatabaseValidation(self)

    def get_connection_params(self):
        """Returns a dict of parameters suitable for get_new_connection."""
        settings_dict = self.settings_dict.copy()
        if settings_dict['NAME'] == '':
            from django.core.exceptions import ImproperlyConfigured
            raise ImproperlyConfigured(
                "settings.DATABASES is improperly configured. "
                "Please supply the NAME value.")
        if not settings_dict['NAME']:
            # if _nodb_connection, connect to master
            settings_dict['NAME'] = 'master'

        autocommit = settings_dict.get('OPTIONS', {}).get('autocommit', False)
        return {
            'connection_string': make_connection_string(settings_dict),
            'timeout': self.command_timeout,
            'use_transactions': not autocommit,
        }

    def get_new_connection(self, conn_params):
        """Opens a connection to the database."""
        self.__connection_string = conn_params.get('connection_string', '')
        conn = Database.connect(**conn_params)
        return conn

    def init_connection_state(self):
        """Initializes the database connection settings."""
        # if 'mars connection=true' in self.__connection_string.lower():
        #     # Issue #41 - Cannot use MARS with savepoints
        #     self.features.uses_savepoints = False
        # cache the properties on the connection
        self.connection.adoConnProperties = dict([(x.Name, x.Value) for x in self.connection.adoConn.Properties])

        try:
            sql_version = int(self.__get_dbms_version().split('.', 2)[0])
        except (IndexError, ValueError):
            warnings.warn(
                "Unable to determine MS SQL server version. Only SQL 2012 or "
                "newer is supported.", DeprecationWarning)
        else:
            if sql_version < VERSION_SQL2012:
                warnings.warn(
                    "This version of MS SQL server is no longer tested with "
                    "django-mssql and not officially supported/maintained.",
                    DeprecationWarning)

    def create_cursor(self):
        """Creates a cursor. Assumes that a connection is established."""
        cursor = self.connection.cursor()
        return cursor

    def _set_autocommit(self, value):
        self.connection.set_autocommit(value)

    def __get_dbms_version(self, make_connection=True):
        """
        Returns the 'DBMS Version' string, or ''. If a connection to the database has not already
        been established, a connection will be made when `make_connection` is True.
        """
        if not self.connection and make_connection:
            self.connect()
        return self.connection.adoConnProperties.get('DBMS Version', '') if self.connection else ''

    def disable_constraint_checking(self):
        """
        Turn off constraint checking for every table
        """
        if self.connection:
            cursor = self.connection.cursor()
        else:
            cursor = self._cursor()
        cursor.execute('EXEC sp_MSforeachtable "ALTER TABLE ? NOCHECK CONSTRAINT all"')
        return True

    def enable_constraint_checking(self):
        """
        Turn on constraint checking for every table
        """
        if self.connection:
            cursor = self.connection.cursor()
        else:
            cursor = self._cursor()
        # don't check the data, just turn them on
        cursor.execute('EXEC sp_MSforeachtable "ALTER TABLE ? WITH NOCHECK CHECK CONSTRAINT all"')

    def check_constraints(self, table_names=None):
        """
        Check the table constraints.
        """
        if self.connection:
            cursor = self.connection.cursor()
        else:
            cursor = self._cursor()
        if not table_names:
            cursor.execute('DBCC CHECKCONSTRAINTS WITH ALL_CONSTRAINTS')
            if cursor.description:
                raise IntegrityError(cursor.fetchall())
        else:
            qn = self.ops.quote_name
            for name in table_names:
                cursor.execute('DBCC CHECKCONSTRAINTS({0}) WITH ALL_CONSTRAINTS'.format(
                    qn(name)
                ))
                if cursor.description:
                    raise IntegrityError(cursor.fetchall())

    # # MS SQL Server doesn't support explicit savepoint commits; savepoints are
    # # implicitly committed with the transaction.
    # # Ignore them.
    def _savepoint_commit(self, sid):
        if self.queries_log:
            self.queries_log.append({
                'sql': '-- RELEASE SAVEPOINT %s -- (because assertNumQueries)' % self.ops.quote_name(sid),
                'time': '0.000',
            })

    def is_usable(self):
        try:
            # Use a mssql cursor directly, bypassing Django's utilities.
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except self.Database.Error:
            return False
        else:
            return True
