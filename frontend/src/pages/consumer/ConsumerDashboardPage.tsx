// Consumer Dashboard Page
import React from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { usePaginated } from '../../hooks/usePaginated'
import { useApi } from '../../hooks/useApi'
import type { ConsumerBooking, Vehicle } from '../../api/types'
import { Card } from '../../components/common/Card'
import { BookingStatusBadge } from '../../components/common/Badge'
import { PageHeader } from '../../components/common/PageHeader'
import { StatTile } from '../../components/common/StatTile'
import { Icon } from '../../components/common/Icon'
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
      <PageHeader
        eyebrow="Driver Dashboard"
        title={`Welcome, ${user?.full_name || 'Driver'}`}
        subtitle="Manage your parking reservations and vehicle profiles"
        actions={
          <>
            <Link to="/consumer/search" className="btn btn-primary btn-md">
              <Icon name="search" size={16} /> Find Parking
            </Link>
            <Link to="/consumer/vehicles" className="btn btn-outline btn-md">
              <Icon name="car" size={16} /> My Vehicles
            </Link>
          </>
        }
      />

      {/* KPI row */}
      <div className="grid grid-cols-3 mb-4">
        <StatTile
          label="Upcoming Bookings"
          value={upcomingBookings.length}
          icon="calendar"
          tone="primary"
          meta="Active reservations"
        />
        <StatTile
          label="Registered Vehicles"
          value={vehicleData?.count ?? '—'}
          icon="car"
          tone="info"
          meta="Linked license plates"
        />
        <StatTile
          label="Active Session"
          value={loadingOngoing ? '…' : activeBooking ? 'In progress' : 'None'}
          icon="clock"
          tone={activeBooking ? 'success' : 'default'}
          meta={activeBooking ? `Slot ${activeBooking.slot_number}` : 'No vehicle parked right now'}
        />
      </div>

      {/* Active ongoing session */}
      {activeBooking && (
        <Card className="session-card">
          <div>
            <div className="badge-row mb-1">
              <span className="badge badge-info">Active parking session</span>
              <span className="font-mono font-semibold">{activeBooking.reference}</span>
            </div>
            <h3 className="card-title">
              {activeBooking.lot_name} — Slot {activeBooking.slot_number}
            </h3>
            <p className="muted-sm mb-0">
              Vehicle <strong>{activeBooking.vehicle_plate}</strong> · Entered{' '}
              {formatDateTime(activeBooking.actual_entry_at || activeBooking.start_time)} · Valid
              until {formatDateTime(activeBooking.end_time)}
            </p>
          </div>
          <Link to={`/consumer/bookings/${activeBooking.id}`} className="btn btn-primary btn-md">
            View Session Details <Icon name="arrowRight" size={15} />
          </Link>
        </Card>
      )}

      {/* Upcoming Bookings */}
      <Card
        title="Upcoming Reservations"
        subtitle="Bookings starting soon"
        action={
          <Link to="/consumer/bookings" className="btn btn-outline btn-sm">
            View all
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
                Reserve a slot
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
                  <th>Start</th>
                  <th>End</th>
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