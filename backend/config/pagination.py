"""Project-wide pagination for list endpoints (D66).

Every collection-list endpoint returns the same envelope:

    {"count": <int>, "next": <url|null>, "previous": <url|null>, "results": [...]}

so a frontend list page can rely on one response shape everywhere. Two
bounded/derived reads opt out with ``pagination_class = None`` -- cities (a
seeded vocabulary) and availability (a computed window set consumed whole).
"""

from rest_framework.pagination import PageNumberPagination

class DefaultPagination(PageNumberPagination):
    """Page-number pagination with a client-tunable, capped page size (D66).

    The default lives here rather than in ``settings.PAGE_SIZE`` so there is a
    single source of truth next to its rationale. ``?page_size=`` lets a client
    widen a page (a slot grid asks for up to ``max_page_size`` rows) but never
    past the cap.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100