// Administrator Platform Reports & Multi-Facility Analytics Page (Phase 8 / D77)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import type { PlatformReport } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatMoney } from '../../lib/format'

export const AdminReportsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const fromParam = searchParams.get('from') || ''
  const toParam = searchParams.get('to') || ''

  const [from, setFrom] = useState(fromParam)
  const [to, setTo] = useState(toParam)

  const queryStr = React.useMemo(() => {
    const sp = new URLSearchParams()
    if (fromParam) sp.set('from', fromParam)
    if (toParam) sp.set('to', toParam)
    const q = sp.toString()
    return q ? `?${q}` : ''
  }, [fromParam, toParam])

  const {
    data: report,
    loading,
    error,
    refetch,
  } = useApi<PlatformReport>(`/reports/platform/${queryStr}`)

  const handleApplyFilter = (e: React.FormEvent) => {
    e.preventDefault()
    const sp = new URLSearchParams()
    if (from) sp.set('from', from)
    if (to) sp.set('to', to)
    setSearchParams(sp)
  }

  const handleReset = () => {
    setFrom('')
    setTo('')
    setSearchParams({})
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Platform Intelligence & Reports</h1>
          <p className="page-subtitle">Platform-wide aggregation covering user cohorts, slot statuses, and revenue</p>
        </div>
      </div>

      <form onSubmit={handleApplyFilter} className="filter-bar">
        <div>
          <input
            type="date"
            className="form-control"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>

        <div>
          <input
            type="date"
            className="form-control"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>

        <Button type="submit" variant="primary">
          Filter Platform Window
        </Button>

        {(fromParam || toParam) && (
          <Button type="button" variant="outline" onClick={handleReset}>
            Reset (Trailing 30d)
          </Button>
        )}
      </form>

      {loading ? (
        <LoadingSpinner message="Synthesizing platform report..." />
      ) : error ? (
        <ErrorState error={error} title="Could not generate report" onRetry={refetch} />
      ) : report ? (
        <>
          <div className="grid grid-cols-4 mb-4">
            <div className="stat-card">
              <div className="stat-label">Active Users</div>
              <div className="stat-value">{report.users.active}</div>
              <div className="stat-meta">{report.users.total} registered accounts</div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Operational Facilities</div>
              <div className="stat-value">{report.lots.active}</div>
              <div className="stat-meta">{report.lots.total} registered facilities</div>
            </div>

            <div className="stat-card" style={{ borderColor: 'var(--success-border)' }}>
              <div className="stat-label" style={{ color: 'var(--success)' }}>Net Revenue</div>
              <div className="stat-value" style={{ color: 'var(--success)' }}>
                {formatMoney(report.revenue.net)}
              </div>
              <div className="stat-meta">Refunded: {formatMoney(report.revenue.refunded)}</div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Platform Occupancy</div>
              <div className="stat-value" style={{ color: 'var(--primary)' }}>
                {((report.occupancy_rate || 0) * 100).toFixed(1)}%
              </div>
              <div className="stat-meta">Aggregate live bay utilization</div>
            </div>
          </div>

          <div className="grid grid-cols-2 mb-4">
            <Card title="User Cohort Composition">
              <div className="table-wrapper">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th className="text-right">Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Consumer Drivers</td>
                      <td className="text-right font-semibold">{report.users.by_role.CONSUMER}</td>
                    </tr>
                    <tr>
                      <td>Facility Managers</td>
                      <td className="text-right font-semibold">{report.users.by_role.MANAGER}</td>
                    </tr>
                    <tr>
                      <td>System Administrators</td>
                      <td className="text-right font-semibold">{report.users.by_role.ADMIN}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Parking Bays Inventory Status">
              <div className="table-wrapper">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Status Category</th>
                      <th className="text-right">Bays</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td><span className="badge badge-success">Available</span></td>
                      <td className="text-right font-semibold">{report.slots.by_status.AVAILABLE}</td>
                    </tr>
                    <tr>
                      <td><span className="badge badge-warning">Physically Occupied</span></td>
                      <td className="text-right font-semibold">{report.slots.by_status.OCCUPIED}</td>
                    </tr>
                    <tr>
                      <td><span className="badge badge-danger">Out of Service</span></td>
                      <td className="text-right font-semibold">{report.slots.by_status.OUT_OF_SERVICE}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  )
}

