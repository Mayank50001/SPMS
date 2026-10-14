"""Reports API views (Phase 8, D73).

Read-only aggregation endpoints. Each view handles only the shared
``?from=&to=&lot=`` filter, delegates the arithmetic to ``services`` and maps the
stable refusal codes to HTTP statuses (PROJECT.md §33). No write verb exists.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrManager, IsAdmin
from apps.bookings.services import BookingRuleError

from .services import (
    ReportError,
    booking_statistics,
    occupancy_aggregation,
    revenue_aggregation,
    platform_report
)

#: Stable refusal code -> HTTP status (Q10). A bad window is 400; a lot outside
#: scope is 404, never 403 (Invariant 3).
REFUSAL_STATUS = {
    "INVALID_WINDOW": status.HTTP_400_BAD_REQUEST,
    "LOT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
}


def _run(aggregate, request, *, uses_lot=True):
    """Run a report aggregate, mapping a refusal to its HTTP status (Q10).

    Every report shares the ``?from=&to=`` period and the same two refusal codes,
    so the plumbing lives here once. ``uses_lot=False`` is for the platform report,
    which is platform-wide by definition and takes no ``?lot=`` (D77).
    """
    kwargs = {
        "user": request.user,
        "from_raw": request.query_params.get("from"),
        "to_raw": request.query_params.get("to"),
    }
    if uses_lot:
        kwargs["lot_raw"] = request.query_params.get("lot")
    try:
        data = aggregate(**kwargs)
    except (ReportError, BookingRuleError) as exc:
        return Response(
            {"error": exc.code, "message": str(exc)},
            status=REFUSAL_STATUS.get(exc.code, status.HTTP_400_BAD_REQUEST),
        )
    return Response(data)


class BookingReportView(APIView):
    """Booking statistics for the caller's scope (8.2, D74).

    ``GET /api/reports/bookings/?from=&to=&lot=`` -> an unpaginated computed
    object (D66 opt-out, like availability and the occupancy board). Manager
    (assigned lots) and Administrator (all); a Consumer is 403 and anonymous is
    401. A ``?lot=`` outside scope is a 404 ``LOT_NOT_FOUND``.
    """

    permission_classes = [IsAdminOrManager]

    def get(self, request):
        return _run(booking_statistics, request)


class RevenueReportView(APIView):
    """Revenue for the caller's scope, from the ledgers (8.3, D75).

    ``GET /api/reports/revenue/?from=&to=&lot=`` -> gross / refunded / net (INR
    strings), the BOOKING/EXTENSION split, the count of failed attempts and the
    recorded-but-uncollected overstay. Same role scoping and window rules as the
    booking report.
    """

    permission_classes = [IsAdminOrManager]

    def get(self, request):
        return _run(revenue_aggregation, request)


class OccupancyReportView(APIView):
    """Occupancy for the caller's scope (8.4, D76).

    ``GET /api/reports/occupancy/?from=&to=&lot=`` -> the live slot summary and a
    windowed booked-rate proxy, clearly separated. Same role scoping and window
    rules as the booking report.
    """

    permission_classes = [IsAdminOrManager]

    def get(self, request):
        return _run(occupancy_aggregation, request)

class PlatformReportView(APIView):
    """The Administrator's platform-wide summary (8.5, D77).

    ``GET /api/reports/platform/?from=&to=`` -> the §29 administrator block:
    user/lot/slot counts plus the composed 8.2-8.4 booking, revenue and occupancy
    figures. Administrator-only (a Manager gets 403) and platform-wide by
    definition, so it accepts no ``?lot=`` (D77).
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        return _run(platform_report, request, uses_lot=False)