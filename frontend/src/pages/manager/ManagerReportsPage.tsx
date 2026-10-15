// Manager Operations Analytics & Reports Page (Phase 8 metric families)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { BookingsReport, RevenueReport, OccupancyReport, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
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
      <div className="page-header">
        <div>
          <h1 className="page-title">Operations Reports & Analytics</h1>
          <p className="page-subtitle">Real-time statistics for bookings, revenue, and bay utilization</p>
        </div>
      </div>

      {/* Date & Facility Filters */}
      <form onSubmit={handleApplyFilter} className="filter-bar">
        <div style={{ minWidth: '180px' }}>
          <select
            className="form-control"
            value={lot}
            onChange={(e) => setLot(e.target.value)}
          >
            <option value="">All Assigned Facilities</option>
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
            placeholder="From Date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>

        <div>
          <input
            type="date"
            className="form-control"
            placeholder="To Date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>

        <Button type="submit" variant="primary">
          Generate Report
        </Button>

        {(lotParam || fromParam || toParam) && (
          <Button type="button" variant="outline" onClick={handleReset}>
            Reset (Trailing 30d)
          </Button>
        )}
      </form>

      {/* Revenue Section */}
      <h2 style={{ fontSize: '1.25rem', marginBottom: '1rem' }}>Financial Revenue Performance</h2>
      {errorRevenue ? (
        <ErrorState error={errorRevenue} title="Revenue report unavailable" onRetry={refetchRevenue} />
      ) : loadingRevenue ? (
        <LoadingSpinner message="Aggregating revenue ledger..." />
      ) : (
        <div className="grid grid-cols-4 mb-4">
          <div className="stat-card" style={{ borderColor: 'var(--success-border)' }}>
            <div className="stat-label" style={{ color: 'var(--success)' }}>Net Revenue</div>
            <div className="stat-value" style={{ color: 'var(--success)' }}>
              {formatMoney(revenueData?.net ?? '0')}
            </div>
            <div className="stat-meta">Settled minus refunds</div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Gross Collected</div>
            <div className="stat-value">{formatMoney(revenueData?.gross ?? '0')}</div>
            <div className="stat-meta">
              Bookings: {formatMoney(revenueData?.by_purpose.BOOKING ?? '0')} · Ext: {formatMoney(revenueData?.by_purpose.EXTENSION ?? '0')}
            </div>
          </div>

          <div className="stat-card">
            <div className="stat-label">Refunded Amount</div>
            <div className="stat-value" style={{ color: 'var(--danger)' }}>
              {formatMoney(revenueData?.refunded ?? '0')}
            </div>
            <div className="stat-meta">Via cancellation cutoff</div>
          </div>

          <div className="stat-card" style={{ background: '#fffbeb', borderColor: '#fde68a' }}>
            <div className="stat-label" style={{ color: '#92400e' }}>Overstay Recorded</div>
            <div className="stat-value" style={{ color: '#92400e' }}>
              {formatMoney(revenueData?.overstay_recorded ?? '0')}
            </div>
            <div className="stat-meta">Recorded debt (not collected)</div>
          </div>
        </div>
      )}

      {/* Bookings & Utilization Grid */}
      <div className="grid grid-cols-2 mb-4">
        {/* Bookings Cohort Breakdown */}
        <Card title="Bookings Cohort Breakdown" subtitle="Current status of reservations created in selected period">
          {errorBookings ? (
            <ErrorState error={errorBookings} title="Bookings report unavailable" onRetry={refetchBookings} />
          ) : loadingBookings ? (
            <LoadingSpinner size="sm" />
          ) : (
            <div>
              <div className="grid grid-cols-2 mb-3">
                <div className="p-3" style={{ background: '#f8fafc', borderRadius: '4px' }}>
                  <div className="text-muted" style={{ fontSize: '0.75rem' }}>TOTAL CREATED</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{bookingsData?.total ?? 0}</div>
                </div>
                <div className="p-3" style={{ background: '#eff6ff', borderRadius: '4px' }}>
                  <div className="text-muted" style={{ fontSize: '0.75rem' }}>ACTIVE NOW IN LOT</div>
                  <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--primary)' }}>
                    {bookingsData?.active_now ?? 0}
                  </div>
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
        <Card title="Bay Occupancy Metrics" subtitle="Real-time physical rate vs windowed reservation proxy">
          {errorOccupancy ? (
            <ErrorState error={errorOccupancy} title="Occupancy metrics unavailable" onRetry={refetchOccupancy} />
          ) : loadingOccupancy ? (
            <LoadingSpinner size="sm" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <div className="text-muted" style={{ fontSize: '0.8125rem' }}>LIVE OCCUPANCY RATE</div>
                <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--primary)', margin: '0.25rem 0' }}>
                  {((occupancyData?.current.rate ?? 0) * 100).toFixed(1)}%
                </div>
                <p style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                  {occupancyData?.current.occupied ?? 0} bays occupied of {occupancyData?.current.total ?? 0} total configured bays right now.
                </p>
              </div>

              <div style={{ padding: '1rem', background: '#f8fafc', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <div className="text-muted" style={{ fontSize: '0.8125rem' }}>WINDOW BOOKED-HOURS PROXY</div>
                <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--warning)', margin: '0.25rem 0' }}>
                  {((occupancyData?.window.booked_rate ?? 0) * 100).toFixed(1)}%
                </div>
                <p style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                  {occupancyData?.window.booked_hours ?? 0} hours booked across {occupancyData?.window.bookings ?? 0} reservations within the window ({occupancyData?.window.bookable_hours ?? 0} total bookable slot hours).
                </p>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

