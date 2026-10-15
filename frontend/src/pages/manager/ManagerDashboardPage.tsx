// Parking Manager Dashboard Page (fanning out to metric families per D81)
import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { BookingsReport, RevenueReport, OccupancyReport, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { formatMoney } from '../../lib/format'

export const ManagerDashboardPage: React.FC = () => {
  const { user } = useAuth()

  // Fan out to metric reports (D81)
  const { data: bookingsReport, loading: loadingBookings, error: errorBookings } = useApi<BookingsReport>('/reports/bookings/')
  const { data: revenueReport, loading: loadingRevenue, error: errorRevenue } = useApi<RevenueReport>('/reports/revenue/')
  const { data: occupancyReport, loading: loadingOccupancy, error: errorOccupancy } = useApi<OccupancyReport>('/reports/occupancy/')

  // Manager's assigned lots
  const { results: lots, loading: loadingLots } = usePaginated<ParkingLot>('/parking-lots/', { pageSize: 5 })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Manager Workspace</h1>
          <p className="page-subtitle">Logged in as {user?.full_name} · Operations Dashboard</p>
        </div>
        <div className="page-actions">
          <Link to="/manager/bookings" className="btn btn-primary">
            Gate Check-in / Out
          </Link>
          <Link to="/manager/lots" className="btn btn-secondary">
            Manage Assigned Lots
          </Link>
        </div>
      </div>

      {/* Primary KPI Metrics */}
      <div className="grid grid-cols-4 mb-4">
        <div className="stat-card" style={errorBookings ? { borderColor: 'var(--danger)' } : undefined}>
          <div className="stat-label">Currently Parked</div>
          <div className="stat-value" style={{ color: errorBookings ? 'var(--danger)' : 'var(--primary)', fontSize: errorBookings ? '1.25rem' : undefined }}>
            {errorBookings ? 'Unavailable' : loadingBookings ? '...' : bookingsReport?.active_now ?? 0}
          </div>
          <div className="stat-meta">{errorBookings ? 'Failed to load metric' : 'Active vehicles in bays'}</div>
        </div>

        <div className="stat-card" style={errorOccupancy ? { borderColor: 'var(--danger)' } : undefined}>
          <div className="stat-label">Live Occupancy Rate</div>
          <div className="stat-value" style={{ color: errorOccupancy ? 'var(--danger)' : 'var(--warning)', fontSize: errorOccupancy ? '1.25rem' : undefined }}>
            {errorOccupancy ? 'Unavailable' : loadingOccupancy ? '...' : `${((occupancyReport?.current.rate ?? 0) * 100).toFixed(1)}%`}
          </div>
          <div className="stat-meta">
            {errorOccupancy ? 'Failed to load metric' : `${occupancyReport?.current.occupied ?? 0} of ${occupancyReport?.current.total ?? 0} bays`}
          </div>
        </div>

        <div className="stat-card" style={errorRevenue ? { borderColor: 'var(--danger)' } : undefined}>
          <div className="stat-label">Net Revenue (30d)</div>
          <div className="stat-value" style={{ color: errorRevenue ? 'var(--danger)' : 'var(--success)', fontSize: errorRevenue ? '1.25rem' : undefined }}>
            {errorRevenue ? 'Unavailable' : loadingRevenue ? '...' : formatMoney(revenueReport?.net ?? '0')}
          </div>
          <div className="stat-meta">{errorRevenue ? 'Failed to load metric' : `Gross: ${formatMoney(revenueReport?.gross ?? '0')}`}</div>
        </div>

        <div className="stat-card" style={errorBookings ? { borderColor: 'var(--danger)' } : undefined}>
          <div className="stat-label">Total Completed</div>
          <div className="stat-value" style={{ color: errorBookings ? 'var(--danger)' : undefined, fontSize: errorBookings ? '1.25rem' : undefined }}>
            {errorBookings ? 'Unavailable' : loadingBookings ? '...' : bookingsReport?.completed ?? 0}
          </div>
          <div className="stat-meta">{errorBookings ? 'Failed to load metric' : `${bookingsReport?.total ?? 0} created in period`}</div>
        </div>
      </div>

      {/* Assigned Lots List */}
      <Card
        title="My Assigned Parking Facilities"
        subtitle="Lots under your direct operational management"
        action={
          <Link to="/manager/lots" className="btn btn-outline btn-sm">
            View All Lots
          </Link>
        }
      >
        {loadingLots ? (
          <LoadingSpinner message="Loading assigned lots..." />
        ) : lots.length === 0 ? (
          <p className="text-muted">No parking facilities currently assigned to your manager account.</p>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Facility Name</th>
                  <th>City</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {lots.map((lot) => (
                  <tr key={lot.id}>
                    <td className="font-mono font-semibold">{lot.code}</td>
                    <td>{lot.name}</td>
                    <td>{lot.city.name}</td>
                    <td>
                      <span className={`badge ${lot.is_active ? 'badge-success' : 'badge-danger'}`}>
                        {lot.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <Link to={`/manager/lots/${lot.id}/occupancy`} className="btn btn-primary btn-sm">
                          Live Board
                        </Link>
                        <Link to={`/manager/lots/${lot.id}/slots`} className="btn btn-outline btn-sm">
                          Slots
                        </Link>
                        <Link to={`/manager/lots/${lot.id}/tariffs`} className="btn btn-outline btn-sm">
                          Pricing
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

