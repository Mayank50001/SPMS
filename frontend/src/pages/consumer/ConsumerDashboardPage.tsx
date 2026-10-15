// Consumer Dashboard Page
import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { usePaginated } from '../../hooks/usePaginated'
import { useApi } from '../../hooks/useApi'
import type { ConsumerBooking, Vehicle } from '../../api/types'
import { Card } from '../../components/common/Card'
import { BookingStatusBadge } from '../../components/common/Badge'
import { formatDateTime, formatMoney } from '../../lib/format'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'

export const ConsumerDashboardPage: React.FC = () => {
  const { user } = useAuth()

  // Fetch upcoming bookings
  const {
    results: upcomingBookings,
    loading: loadingBookings,
    error: errorBookings,
  } = usePaginated<ConsumerBooking>('/bookings/', {
    params: { scope: 'upcoming', ordering: 'start_time' },
    pageSize: 5,
  })

  // Fetch ongoing booking (if any)
  const {
    results: ongoingBookings,
    loading: loadingOngoing,
  } = usePaginated<ConsumerBooking>('/bookings/', {
    params: { scope: 'ongoing' },
    pageSize: 1,
  })

  // Fetch vehicle count
  const {
    data: vehicleData,
  } = useApi<{ count: number; results: Vehicle[] }>('/vehicles/?page_size=1')

  const activeBooking = ongoingBookings[0]

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Welcome, {user?.full_name || 'Driver'}</h1>
          <p className="page-subtitle">Manage your parking reservations and vehicle profiles</p>
        </div>
        <div className="page-actions">
          <Link to="/consumer/search" className="btn btn-primary">
            Find Parking
          </Link>
          <Link to="/consumer/vehicles" className="btn btn-secondary">
            My Vehicles
          </Link>
        </div>
      </div>

      {/* Active ongoing booking banner */}
      {loadingOngoing ? (
        <LoadingSpinner size="sm" />
      ) : activeBooking ? (
        <div
          className="mb-4 p-4"
          style={{
            background: '#eff6ff',
            border: '2px solid #3b82f6',
            borderRadius: '8px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '1rem',
          }}
        >
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
              <span className="badge badge-info">Active Parking Session</span>
              <span className="font-mono" style={{ fontWeight: 600 }}>{activeBooking.reference}</span>
            </div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
              {activeBooking.lot_name} — Slot {activeBooking.slot_number}
            </h3>
            <p className="text-muted" style={{ fontSize: '0.875rem' }}>
              Vehicle: <strong>{activeBooking.vehicle_plate}</strong> · Entered at: {formatDateTime(activeBooking.actual_entry_at || activeBooking.start_time)} · Valid until: {formatDateTime(activeBooking.end_time)}
            </p>
          </div>
          <Link to={`/consumer/bookings/${activeBooking.id}`} className="btn btn-primary">
            View Session Details
          </Link>
        </div>
      ) : null}

      {/* Quick Stats Grid */}
      <div className="grid grid-cols-3 mb-4">
        <div className="stat-card">
          <div className="stat-label">Upcoming Bookings</div>
          <div className="stat-value">{upcomingBookings.length}</div>
          <div className="stat-meta">Active reservations</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Registered Vehicles</div>
          <div className="stat-value">{vehicleData?.count ?? '—'}</div>
          <div className="stat-meta">Linked license plates</div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Current Time (IST)</div>
          <div className="stat-value" style={{ fontSize: '1.25rem', marginTop: '0.65rem' }}>
            {new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })}
          </div>
          <div className="stat-meta">Asia/Kolkata business zone</div>
        </div>
      </div>

      {/* Upcoming Bookings Section */}
      <Card
        title="Upcoming Reservations"
        subtitle="Bookings starting soon"
        action={
          <Link to="/consumer/bookings" className="btn btn-outline btn-sm">
            View All Bookings
          </Link>
        }
      >
        {loadingBookings ? (
          <LoadingSpinner message="Loading upcoming bookings..." />
        ) : errorBookings ? (
          <p className="text-danger">Failed to load upcoming reservations.</p>
        ) : upcomingBookings.length === 0 ? (
          <EmptyState
            title="No upcoming bookings"
            message="You don't have any parking slots reserved for future dates."
            action={
              <Link to="/consumer/search" className="btn btn-primary btn-sm">
                Reserve a Slot Now
              </Link>
            }
          />
        ) : (
          <div className="table-wrapper">
            <table className="table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Parking Lot</th>
                  <th>Slot</th>
                  <th>Vehicle</th>
                  <th>Start Time</th>
                  <th>End Time</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {upcomingBookings.map((b) => (
                  <tr key={b.id}>
                    <td className="font-mono font-semibold">{b.reference}</td>
                    <td>{b.lot_name}</td>
                    <td>Slot {b.slot_number}</td>
                    <td>{b.vehicle_plate}</td>
                    <td>{formatDateTime(b.start_time)}</td>
                    <td>{formatDateTime(b.end_time)}</td>
                    <td className="font-semibold">{formatMoney(b.base_amount)}</td>
                    <td>
                      <BookingStatusBadge status={b.effective_status} />
                    </td>
                    <td>
                      <Link to={`/consumer/bookings/${b.id}`} className="btn btn-outline btn-sm">
                        Details
                      </Link>
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
