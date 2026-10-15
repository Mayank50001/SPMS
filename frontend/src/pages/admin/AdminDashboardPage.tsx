// Administrator System Dashboard Page (Platform Report per D77)
import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { useApi } from '../../hooks/useApi'
import type { PlatformReport } from '../../api/types'
import { Card } from '../../components/common/Card'
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
      <div className="page-header">
        <div>
          <h1 className="page-title">Platform Administration</h1>
          <p className="page-subtitle">Welcome, {user?.full_name} · System-wide Oversight & Governance</p>
        </div>
        <div className="page-actions">
          <Link to="/admin/lots" className="btn btn-primary">
            + New Facility
          </Link>
          <Link to="/admin/rules" className="btn btn-secondary">
            Business Policies
          </Link>
        </div>
      </div>

      {loading ? (
        <LoadingSpinner message="Aggregating platform metrics..." />
      ) : error ? (
        <ErrorState error={error} title="Could not load platform metrics" onRetry={refetch} />
      ) : platform ? (
        <>
          {/* Top High-level KPI Cards */}
          <div className="grid grid-cols-4 mb-4">
            <div className="stat-card">
              <div className="stat-label">Total Users</div>
              <div className="stat-value">{platform.users.total}</div>
              <div className="stat-meta">
                {platform.users.by_role.CONSUMER} Consumers · {platform.users.by_role.MANAGER} Managers · {platform.users.by_role.ADMIN} Admins
              </div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Parking Facilities</div>
              <div className="stat-value" style={{ color: 'var(--primary)' }}>
                {platform.lots.total}
              </div>
              <div className="stat-meta">{platform.lots.active} active lots in operation</div>
            </div>

            <div className="stat-card">
              <div className="stat-label">Total Parking Bays</div>
              <div className="stat-value">{platform.slots.total}</div>
              <div className="stat-meta">
                {platform.slots.by_status.AVAILABLE} Available · {platform.slots.by_status.OCCUPIED} Occupied
              </div>
            </div>

            <div className="stat-card" style={{ borderColor: 'var(--success-border)' }}>
              <div className="stat-label" style={{ color: 'var(--success)' }}>Net Revenue (30d)</div>
              <div className="stat-value" style={{ color: 'var(--success)' }}>
                {formatMoney(platform.revenue.net)}
              </div>
              <div className="stat-meta">Gross: {formatMoney(platform.revenue.gross)}</div>
            </div>
          </div>

          {/* Operational Breakdown Grid */}
          <div className="grid grid-cols-2 mb-4">
            <Card title="Reservations & Sessions" subtitle="Cohort activity for trailing 30 days">
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
                <div className="flex justify-between">
                  <span className="text-muted">Total Reservations Created</span>
                  <span className="font-semibold" style={{ fontSize: '1.125rem' }}>
                    {platform.bookings.total}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Vehicles Currently in Bays (Active Now)</span>
                  <span className="font-semibold text-primary" style={{ fontSize: '1.125rem' }}>
                    {platform.bookings.active_now}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Successfully Completed Sessions</span>
                  <span>{platform.bookings.completed}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted">Cancelled Bookings</span>
                  <span>{platform.bookings.cancelled}</span>
                </div>
                <div className="flex justify-between" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
                  <span className="text-muted">Platform Utilization Rate</span>
                  <span className="font-semibold">
                    {((platform.occupancy_rate || 0) * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            </Card>

            <Card title="Quick Management Navigation" subtitle="Jump directly into operational workflows">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <Link to="/admin/users" className="btn btn-outline" style={{ justifyContent: 'flex-start', padding: '0.75rem' }}>
                  👥 User Accounts
                </Link>
                <Link to="/admin/managers" className="btn btn-outline" style={{ justifyContent: 'flex-start', padding: '0.75rem' }}>
                  👔 Manager Roster
                </Link>
                <Link to="/admin/lots" className="btn btn-outline" style={{ justifyContent: 'flex-start', padding: '0.75rem' }}>
                  🅿️ Parking Facilities
                </Link>
                <Link to="/admin/rules" className="btn btn-outline" style={{ justifyContent: 'flex-start', padding: '0.75rem' }}>
                  ⚙️ Business Policies
                </Link>
                <Link to="/admin/bookings" className="btn btn-outline" style={{ justifyContent: 'flex-start', padding: '0.75rem' }}>
                  📋 All Bookings
                </Link>
                <Link to="/admin/transactions" className="btn btn-outline" style={{ justifyContent: 'flex-start', padding: '0.75rem' }}>
                  💳 Financial Ledger
                </Link>
              </div>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  )
}

