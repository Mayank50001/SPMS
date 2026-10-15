// Manager Operations Analytics & Reports Page (Phase 8 metric families)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { BookingsReport, RevenueReport, OccupancyReport, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { StatTile } from '../../components/common/StatTile'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatMoney } from '../../lib/format'

export const ManagerReportsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const lotParam = searchParams.get('lot') || ''
  const fromParam = searchParams.get('from') || ''
  const toParam = searchParams.get('to') || ''

  const [lot, setLot] = useState(lotParam)
  const [from, setFrom] = useState(fromParam)
  const [to, setTo] = useState(toParam)

  // Fetch manager's assigned lots for filter
  const { results: lots } = usePaginated<ParkingLot>('/parking-lots/', { pageSize: 100 })

  // Construct query string
  const queryStr = React.useMemo(() => {
    const sp = new URLSearchParams()
    if (lotParam) sp.set('lot', lotParam)
    if (fromParam) sp.set('from', fromParam)
    if (toParam) sp.set('to', toParam)
    const q = sp.toString()
    return q ? `?${q}` : ''
  }, [lotParam, fromParam, toParam])

  // Fan out to metric families (D81 error isolated)
  const { data: bookingsData, loading: loadingBookings, error: errorBookings, refetch: refetchBookings } = useApi<BookingsReport>(`/reports/bookings/${queryStr}`)
  const { data: revenueData, loading: loadingRevenue, error: errorRevenue, refetch: refetchRevenue } = useApi<RevenueReport>(`/reports/revenue/${queryStr}`)
  const { data: occupancyData, loading: loadingOccupancy, error: errorOccupancy, refetch: refetchOccupancy } = useApi<OccupancyReport>(`/reports/occupancy/${queryStr}`)

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault()
    const sp = new URLSearchParams()
    if (lot) sp.set('lot', lot)
    if (from) sp.set('from', from)
    if (to) sp.set('to', to)
    setSearchParams(sp)
  }

  const handleReset = () => {
    setLot('')
    setFrom('')
    setTo('')
    setSearchParams({})
  }

  return (
    <div>
      <PageHeader
        eyebrow="Analytics"
        title="Operations reports"
        subtitle="Bookings, revenue and bay-utilization statistics for your facilities"
      />

      {/* Date & Facility Filters */}
      <form onSubmit={handleApplyFilter} className="filter-bar">
        <div style={{ minWidth: '200px' }}>
          <select className="form-control" value={lot} onChange={(e) => setLot(e.target.value)}>
            <option value="">All assigned facilities</option>
            {lots.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.code})
              </option>
            ))}
          </select>
        </div>

        <div>
          <input
            type="date"
            className="form-control"
            placeholder="From date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>

        <div>
          <input
            type="date"
            className="form-control"
            placeholder="To date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>

        <Button type="submit" variant="primary">
          <Icon name="chart" size={16} /> Generate report
        </Button>

        {(lotParam || fromParam || toParam) && (
          <Button type="button" variant="outline" onClick={handleReset}>
            <Icon name="close" size={16} /> Reset (trailing 30d)
          </Button>
        )}
      </form>

      {/* Revenue Section */}
      <h2 className="section-title">Financial revenue performance</h2>
      {errorRevenue ? (
        <ErrorState error={errorRevenue} title="Revenue report unavailable" onRetry={refetchRevenue} />
      ) : loadingRevenue ? (
        <LoadingSpinner message="Aggregating revenue ledger..." />
      ) : (
        <div className="grid grid-cols-4 mb-4">
          <StatTile
            label="Net revenue"
            value={formatMoney(revenueData?.net ?? '0')}
            icon="wallet"
            tone="success"
            meta="Settled minus refunds"
          />
          <StatTile
            label="Gross collected"
            value={formatMoney(revenueData?.gross ?? '0')}
            icon="receipt"
            tone="default"
            meta={
              <>
                Bookings {formatMoney(revenueData?.by_purpose.BOOKING ?? '0')} · Ext{' '}
                {formatMoney(revenueData?.by_purpose.EXTENSION ?? '0')}
              </>
            }
          />
          <StatTile
            label="Refunded amount"
            value={formatMoney(revenueData?.refunded ?? '0')}
            icon="logout"
            tone="danger"
            meta="Via cancellation cutoff"
          />
          <StatTile
            label="Overstay recorded"
            value={formatMoney(revenueData?.overstay_recorded ?? '0')}
            icon="clock"
            tone="warning"
            meta="Recorded debt (not collected)"
          />
        </div>
      )}

      {/* Bookings & Utilization Grid */}
      <div className="grid grid-cols-2 mb-4">
        {/* Bookings Cohort Breakdown */}
        <Card title="Bookings cohort" subtitle="Status of reservations created in the selected period">
          {errorBookings ? (
            <ErrorState error={errorBookings} title="Bookings report unavailable" onRetry={refetchBookings} />
          ) : loadingBookings ? (
            <LoadingSpinner size="sm" />
          ) : (
            <div>
              <div className="grid grid-cols-2 mb-3">
                <div className="mini-stat">
                  <div className="mini-stat-label">Total created</div>
                  <div className="mini-stat-value">{bookingsData?.total ?? 0}</div>
                </div>
                <div className="mini-stat">
                  <div className="mini-stat-label">Active now in lot</div>
                  <div className="mini-stat-value text-primary">{bookingsData?.active_now ?? 0}</div>
                </div>
              </div>

              {bookingsData?.by_status && (
                <div className="table-wrapper">
                  <table className="table">
                    <thead>
                      <tr>
                        <th>Status</th>
                        <th className="text-right">Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(bookingsData.by_status).map(([st, cnt]) => (
                        <tr key={st}>
                          <td>{st}</td>
                          <td className="text-right font-semibold">{cnt}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* Occupancy Utilization */}
        <Card title="Bay occupancy" subtitle="Live physical rate vs windowed reservation proxy">
          {errorOccupancy ? (
            <ErrorState error={errorOccupancy} title="Occupancy metrics unavailable" onRetry={refetchOccupancy} />
          ) : loadingOccupancy ? (
            <LoadingSpinner size="sm" />
          ) : (
            <div className="stack">
              <div className="mini-stat">
                <div className="mini-stat-label">Live occupancy rate</div>
                <div className="mini-stat-value text-primary">
                  {((occupancyData?.current.rate ?? 0) * 100).toFixed(1)}%
                </div>
                <p className="muted-sm mb-0">
                  {occupancyData?.current.occupied ?? 0} bays occupied of{' '}
                  {occupancyData?.current.total ?? 0} configured bays right now.
                </p>
              </div>

              <div className="mini-stat">
                <div className="mini-stat-label">Window booked-hours proxy</div>
                <div className="mini-stat-value" style={{ color: 'var(--warning)' }}>
                  {((occupancyData?.window.booked_rate ?? 0) * 100).toFixed(1)}%
                </div>
                <p className="muted-sm mb-0">
                  {occupancyData?.window.booked_hours ?? 0} hours booked across{' '}
                  {occupancyData?.window.bookings ?? 0} reservations within the window (
                  {occupancyData?.window.bookable_hours ?? 0} total bookable slot hours).
                </p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}