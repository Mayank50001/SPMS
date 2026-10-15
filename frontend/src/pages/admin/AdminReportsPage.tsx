// Administrator Platform Reports & Multi-Facility Analytics Page (Phase 8 / D77)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import type { PlatformReport } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { StatTile } from '../../components/common/StatTile'
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
      <PageHeader
        eyebrow="Analytics"
        title="Platform intelligence"
        subtitle="Platform-wide aggregation covering user cohorts, slot statuses and revenue"
      />

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
          <Icon name="chart" size={16} /> Filter platform window
        </Button>

        {(fromParam || toParam) && (
          <Button type="button" variant="outline" onClick={handleReset}>
            <Icon name="close" size={16} /> Reset (trailing 30d)
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
            <StatTile
              label="Active users"
              value={report.users.active}
              icon="users"
              tone="primary"
              meta={`${report.users.total} registered accounts`}
            />
            <StatTile
              label="Operational facilities"
              value={report.lots.active}
              icon="building"
              tone="info"
              meta={`${report.lots.total} registered facilities`}
            />
            <StatTile
              label="Net revenue"
              value={formatMoney(report.revenue.net)}
              icon="wallet"
              tone="success"
              meta={`Refunded: ${formatMoney(report.revenue.refunded)}`}
            />
            <StatTile
              label="Platform occupancy"
              value={`${((report.occupancy_rate || 0) * 100).toFixed(1)}%`}
              icon="grid"
              tone="warning"
              meta="Aggregate live bay utilization"
            />
          </div>

          <div className="grid grid-cols-2 mb-4">
            <Card title="User cohort composition" subtitle="Accounts by role">
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
                      <td>Consumer drivers</td>
                      <td className="text-right font-semibold">{report.users.by_role.CONSUMER}</td>
                    </tr>
                    <tr>
                      <td>Facility managers</td>
                      <td className="text-right font-semibold">{report.users.by_role.MANAGER}</td>
                    </tr>
                    <tr>
                      <td>System administrators</td>
                      <td className="text-right font-semibold">{report.users.by_role.ADMIN}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Card>

            <Card title="Parking bays inventory" subtitle="Bays by physical status">
              <div className="table-wrapper">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Status category</th>
                      <th className="text-right">Bays</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>
                        <Badge variant="success">Available</Badge>
                      </td>
                      <td className="text-right font-semibold">{report.slots.by_status.AVAILABLE}</td>
                    </tr>
                    <tr>
                      <td>
                        <Badge variant="warning">Physically occupied</Badge>
                      </td>
                      <td className="text-right font-semibold">{report.slots.by_status.OCCUPIED}</td>
                    </tr>
                    <tr>
                      <td>
                        <Badge variant="danger">Out of service</Badge>
                      </td>
                      <td className="text-right font-semibold">
                        {report.slots.by_status.OUT_OF_SERVICE}
                      </td>
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