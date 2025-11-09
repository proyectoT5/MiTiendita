"""
This file contains Microsoft SQL Server specific aggregates and overrides for
the default Django aggregates.
"""

from django.db.models.aggregates import Avg, StdDev, Variance
from django.db.models.expressions import Value
from django.db.models.functions import Length, Substr


def as_microsoft(expression):
    """
    Decorated function is added to the provided expression as the Microsoft
    vender specific as_sql override.
    """
    def dec(func):
        setattr(expression, 'as_microsoft', func)
        return func
    return dec


# Aggregates
@as_microsoft(Avg)
def cast_avg_to_float(self, compiler, connection):
    """
    Microsoft AVG doesn't cast type by default, but needs to CAST to FLOAT so
    that AVG([1, 2]) == 1.5, instead of 1.
    """
    if getattr(connection, 'cast_avg_to_float', True):
        return self.as_sql(compiler, connection, template='%(function)s(CAST(%(field)s AS FLOAT))')
    return self.as_sql(compiler, connection)


@as_microsoft(StdDev)
def fix_stddev_function_name(self, compiler, connection):
    """
    Fix function names to 'STDEV' or 'STDEVP' as used by mssql
    """
    function = 'STDEV'
    if self.function == 'STDDEV_POP':
        function = 'STDEVP'
    return self.as_sql(compiler, connection, function=function)


@as_microsoft(Variance)
def fix_variance_function_name(self, compiler, connection):
    """
    Fix function names to 'VAR' or 'VARP' as used by mssql
    """
    function = 'VAR'
    if self.function == 'VAR_POP':
        function = 'VARP'
    return self.as_sql(compiler, connection, function=function)


# Expressions


# Functions
@as_microsoft(Length)
def fix_length_function_name(self, compiler, connection):
    """
    T-SQL LEN()
    """
    self.function = 'LEN'
    return self.as_sql(compiler, connection)


@as_microsoft(Substr)
def ensure_three_substring_arguments(self, compiler, connection):
    """
    T-SQL SUBSTRING() requires 3 arguments. length is never implied.
    """
    if len(self.source_expressions) == 2:
        self.source_expressions.append(Value(2 ** 31 - 1))
    return self.as_sql(compiler, connection)
