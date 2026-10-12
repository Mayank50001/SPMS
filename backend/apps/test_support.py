"""Shared test helpers.

D66 made every collection-list endpoint return the DRF pagination envelope:

    {"count": ..., "next": ..., "previous": ..., "results": [...]}

Most tests care about the rows, not the wrapper. ``page_rows`` returns the rows
for a paginated list response and passes a plain object (a detail read, a write
response, an error) through unchanged, so a test does not need to know which
shape it is holding.
"""


def page_rows(response):
    """The rows of a D66 paginated list response, or the body itself."""
    data = response.data
    if isinstance(data, dict) and "results" in data:
        return data["results"]
    return data