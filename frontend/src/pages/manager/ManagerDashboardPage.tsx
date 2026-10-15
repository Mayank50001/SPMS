// Parking Manager Dashboard Page (fanning out to metric families per D81)
import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { BookingsReport, RevenueReport, OccupancyReport, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { StatTile } from '../../components/common/StatTile'
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

  const occ = occupancyReport?.current
  const occTotal = occ?.total ?? 0
  const pct = (n: number) => (occTotal > 0 ? `${(n / occTotal) * 100}%` : '0%')

  return (
    <div>
      <PageHeader
        eyebrow="Manager workspace"
        title={`Welcome, ${user?.full_name || 'Manager'}`}
        subtitle="Operations dashboard for your assigned parking facilities"
        actions={
          <>
            <Link to="/manager/bookings" className="btn btn-primary btn-md">
              <Icon name="ticket" size={16} /> Gate check-in / out
            </Link>
            <Link to="/manager/lots" className="btn btn-outline btn-md">
              <Icon name="building" size={16} /> My facilities
            </Link>
          </>
        }
      />

      {/* Primary KPI Metrics */}
      <div className="grid grid-cols-4 mb-4">
        <StatTile
          label="Currently parked"
          icon="car"
          tone="primary"
          value={
            errorBookings ? (
              <span className="text-danger" style={{ fontSize: '1.1rem' }}>Unavailable</span>
            ) : loadingBookings ? (
              '…'
            ) : (
              bookingsReport?.active_now ?? 0
            )
          }
          meta={errorBookings ? 'Failed to load metric' : 'Active vehicles in bays'}
        />

        <StatTile
          label="Live occupancy"
          icon="grid"
          tone="warning"
          value={
            errorOccupancy ? (
              <span className="text-danger" style={{ fontSize: '1.1rem' }}>Unavailable</span>
            ) : loadingOccupancy ? (
              '…'
            ) : (
              `${((occupancyReport?.current.rate ?? 0) * 100).toFixed(1)}%`
            )
          }
          meta={
            errorOccupancy
              ? 'Failed to load metric'
              : `${occ?.occupied ?? 0} of ${occ?.total ?? 0} bays`
          }
        />

        <StatTile
          label="Net revenue (30d)"
          icon="wallet"
          tone="success"
          value={
            errorRevenue ? (
              <span className="text-danger" style={{ fontSize: '1.1rem' }}>Unavailable</span>
            ) : loadingRevenue ? (
              '…'
            ) : (
              formatMoney(revenueReport?.net ?? '0')
            )
          }
          meta={errorRevenue ? 'Failed to load metric' : `Gross: ${formatMoney(revenueReport?.gross ?? '0')}`}
        />

        <StatTile
          label="Total completed"
          icon="check"
          tone="info"
          value={
            errorBookings ? (
              <span className="text-danger" style={{ fontSize: '1.1rem' }}>Unavailable</span>
            ) : loadingBookings ? (
              '…'
            ) : (
              bookingsReport?.completed ?? 0
            )
          }
          meta={errorBookings ? 'Failed to load metric' : `${bookingsReport?.total ?? 0} created in period`}
        />
      </div>

      {/* Live occupancy breakdown */}
      {!loadingOccupancy && !errorOccupancy && occ && occTotal > 0 && (
        <Card
          title="Live occupancy breakdown"
          subtitle={`${occ.occupied} of ${occ.total} bays occupied · ${(occ.rate * 100).toFixed(1)}% full`}
        >
          <div className="occ-bar">
            <div className="occ-seg occ-seg-occupied" style={{ width: pct(occ.occupied) }} />
            <div className="occ-seg occ-seg-available" style={{ width: pct(occ.available) }} />
            <div className="occ-seg occ-seg-oos" style={{ width: pct(occ.out_of_service) }} />
          </div>
          <div className="legend">
            <span className="legend-item">
              <span className="legend-dot occ-seg-occupied" /> Occupied {occ.occupied}
            </span>
            <span className="legend-item">
              <span className="legend-dot occ-seg-available" /> Available {occ.available}
            </span>
            <span className="legend-item">
              <span className="legend-dot occ-seg-oos" /> Out of service {occ.out_of_service}
            </span>
          </div>
        </Card>
      )}

      {/* Assigned Lots List */}
      <Card
        title="My assigned parking facilities"
        subtitle="Lots under your direct operational management"
        action={
          <Link to="/manager/lots" className="btn btn-outline btn-sm">
            View all lots
          </Link>
        }
      >
        {loadingLots ? (
          <LoadingSpinner message="Loading assigned lots..." />
        ) : lots.length === 0 ? (
          <p className="text-muted">No parking facilities are currently assigned to your manager account.</p>
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Facility name</th>
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
                      <Badge variant={lot.is_active ? 'success' : 'danger'}>
                        {lot.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td>
                      <div className="toolbar">
                        <Link to={`/manager/lots/${lot.id}/occupancy`} className="btn btn-primary btn-sm">
                          Live board
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