from django.db.backends.base.features import BaseDatabaseFeatures
from django.db.utils import InterfaceError as DjangoInterfaceError
from django.utils.functional import cached_property


try:
    import pytz
except ImportError:
    pytz = None


class DatabaseFeatures(BaseDatabaseFeatures):
    uses_custom_query_class = True
    has_bulk_insert = True

    # DateTimeField doesn't support timezones, only DateTimeOffsetField
    supports_timezones = False
    supports_sequence_reset = False

    can_return_id_from_insert = True

    supports_regex_backreferencing = False

    supports_tablespaces = True

    supports_nullable_unique_constraints = False
    supports_partially_nullable_unique_constraints = False

    can_introspect_autofield = True
    can_introspect_small_integer_field = True

    supports_subqueries_in_group_by = False

    allow_sliced_subqueries = False

    uses_savepoints = True

    supports_paramstyle_pyformat = False

    closed_cursor_error_class = DjangoInterfaceError

    requires_literal_defaults = True

    has_native_uuid_field = True

    @cached_property
    def has_zoneinfo_database(self):
        return pytz is not None

    # Dict of test import path and list of versions on which it fails
    failing_tests = {
        # Some tests are known to fail with django-mssql.
        'aggregation.tests.BaseAggregateTestCase.test_decimal_max_digits_has_no_effect': [(1, 8)],
        'aggregation.tests.ComplexAggregateTestCase.test_expression_on_aggregation': [(1, 8)],

        # MSSQL throws an arithmetic overflow error.
        'expressions.tests.ExpressionOperatorTests.test_righthand_power': [(1, 8)],

        # MSSQL supports more than the long name length of 71 that is asserted
        'invalid_models_tests.tests.FieldNamesTests.test_M2M_long_column_name': [(1, 8)],

        # MSSQL doesn't allow changing a field in to an IDENTITY field.
        'schema.tests.SchemaTests.test_alter_int_pk_to_autofield_pk': [(1, 8)],
    }
