// Administrator System Dashboard Page (Platform Report per D77)
import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { useApi } from '../../hooks/useApi'
import type { PlatformReport } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { StatTile } from '../../components/common/StatTile'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatMoney } from '../../lib/format'

export const AdminDashboardPage: React.FC = () => {
  const { user } = useAuth()

  // Platform report (Admin only, D77)
  const {
    data: platform,
    loading,
    error,
    refetch,
  } = useApi<PlatformReport>('/reports/platform/')

  return (
    <div>
      <PageHeader
        eyebrow="Platform admin"
        title={`Welcome, ${user?.full_name || 'Administrator'}`}
        subtitle="System-wide oversight and governance"
        actions={
          <>
            <Link to="/admin/lots" className="btn btn-primary btn-md">
              <Icon name="plus" size={16} /> New facility
            </Link>
            <Link to="/admin/rules" className="btn btn-outline btn-md">
              <Icon name="sliders" size={16} /> Business policies
            </Link>
          </>
        }
      />

      {loading ? (
        <LoadingSpinner message="Aggregating platform metrics..." />
      ) : error ? (
        <ErrorState error={error} title="Could not load platform metrics" onRetry={refetch} />
      ) : platform ? (
        <>
          {/* Top High-level KPI Cards */}
          <div className="grid grid-cols-4 mb-4">
            <StatTile
              label="Total users"
              value={platform.users.total}
              icon="users"
              tone="primary"
              meta={
                <>
                  {platform.users.by_role.CONSUMER} consumers · {platform.users.by_role.MANAGER}{' '}
                  managers · {platform.users.by_role.ADMIN} admins
                </>
              }
            />
            <StatTile
              label="Parking facilities"
              value={platform.lots.total}
              icon="building"
              tone="info"
              meta={`${platform.lots.active} active lots in operation`}
            />
            <StatTile
              label="Total parking bays"
              value={platform.slots.total}
              icon="grid"
              tone="default"
              meta={
                <>
                  {platform.slots.by_status.AVAILABLE} available ·{' '}
                  {platform.slots.by_status.OCCUPIED} occupied
                </>
              }
            />
            <StatTile
              label="Net revenue (30d)"
              value={formatMoney(platform.revenue.net)}
              icon="wallet"
              tone="success"
              meta={`Gross: ${formatMoney(platform.revenue.gross)}`}
            />
          </div>

          {/* Operational Breakdown Grid */}
          <div className="grid grid-cols-2 mb-4">
            <Card title="Reservations &amp; sessions" subtitle="Cohort activity for the trailing 30 days">
              <div className="info-list">
                <div className="info-row">
                  <span className="info-label">Total reservations created</span>
                  <span className="info-value">{platform.bookings.total}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Vehicles currently in bays</span>
                  <span className="info-value text-primary">{platform.bookings.active_now}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Successfully completed sessions</span>
                  <span className="info-value">{platform.bookings.completed}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Cancelled bookings</span>
                  <span className="info-value">{platform.bookings.cancelled}</span>
                </div>
                <div className="info-row">
                  <span className="info-label">Platform utilization rate</span>
                  <span className="info-value">
                    {((platform.occupancy_rate || 0) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </Card>

            <Card title="Quick management" subtitle="Jump directly into operational workflows">
              <div className="quick-links">
                <Link to="/admin/users" className="quick-link">
                  <Icon name="users" size={18} /> User accounts
                </Link>
                <Link to="/admin/managers" className="quick-link">
                  <Icon name="user" size={18} /> Manager roster
                </Link>
                <Link to="/admin/lots" className="quick-link">
                  <Icon name="building" size={18} /> Parking facilities
                </Link>
                <Link to="/admin/rules" className="quick-link">
                  <Icon name="sliders" size={18} /> Business policies
                </Link>
                <Link to="/admin/bookings" className="quick-link">
                  <Icon name="list" size={18} /> All bookings
                </Link>
                <Link to="/admin/transactions" className="quick-link">
                  <Icon name="wallet" size={18} /> Financial ledger
                </Link>
              </div>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  )
}