from __future__ import unicode_literals


#25894 Evaluation of zero-length slices of queryset.values() fails
def set_limits(self, low=None, high=None):
    self._original_set_limits(low, high)
    if self.low_mark == self.high_mark:
        self.set_empty()

from django.db.models.sql.query import Query
Query._original_set_limits = Query.set_limits
Query.set_limits = set_limits