// Consumer My Bookings Page
import React, { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import type { ConsumerBooking, BookingStatus } from '../../api/types'
import { Card } from '../../components/common/Card'
import { BookingStatusBadge } from '../../components/common/Badge'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { formatMoney, formatDateTime } from '../../lib/format'

export const MyBookingsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const scopeParam = searchParams.get('scope') || ''
  const statusParam = searchParams.get('status') || ''
  const orderingParam = searchParams.get('ordering') || '-start_time'

  const [scope, setScope] = useState(scopeParam)
  const [status, setStatus] = useState(statusParam)
  const [ordering, setOrdering] = useState(orderingParam)

  const {
    results: bookings,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
  } = usePaginated<ConsumerBooking>('/bookings/', {
    params: {
      scope: scopeParam || undefined,
      status: statusParam || undefined,
      ordering: orderingParam || undefined,
    },
  })

  const handleFilterChange = (newScope: string, newStatus: string, newOrdering: string) => {
    const sp = new URLSearchParams()
    if (newScope) sp.set('scope', newScope)
    if (newStatus) sp.set('status', newStatus)
    if (newOrdering) sp.set('ordering', newOrdering)
    setSearchParams(sp)
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">My Bookings</h1>
          <p className="page-subtitle">View and manage your parking reservations</p>
        </div>
        <div className="page-actions">
          <Link to="/consumer/search" className="btn btn-primary">
            + Book New Slot
          </Link>
        </div>
      </div>

      {/* Filter Tabs & Selectors */}
      <div className="filter-bar">
        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
          {[
            { label: 'All Bookings', value: '' },
            { label: 'Upcoming', value: 'upcoming' },
            { label: 'Ongoing', value: 'ongoing' },
            { label: 'Past', value: 'past' },
          ].map((tab) => (
            <button
              key={tab.value}
              type="button"
              className={`btn btn-sm ${scope === tab.value ? 'btn-primary' : 'btn-outline'}`}
              onClick={() => {
                setScope(tab.value)
                handleFilterChange(tab.value, status, ordering)
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <select
            className="form-control"
            style={{ width: 'auto' }}
            value={status}
            onChange={(e) => {
              setStatus(e.target.value)
              handleFilterChange(scope, e.target.value, ordering)
            }}
          >
            <option value="">All Statuses</option>
            <option value="PENDING_PAYMENT">Pending Payment</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="COMPLETED">Completed</option>
            <option value="CANCELLED">Cancelled</option>
            <option value="EXPIRED">Expired</option>
          </select>

          <select
            className="form-control"
            style={{ width: 'auto' }}
            value={ordering}
            onChange={(e) => {
              setOrdering(e.target.value)
              handleFilterChange(scope, status, e.target.value)
            }}
          >
            <option value="-start_time">Start Time (Newest First)</option>
            <option value="start_time">Start Time (Earliest First)</option>
            <option value="-created_at">Booked Date (Newest First)</option>
          </select>
        </div>
      </div>

      {/* Bookings Table */}
      <Card>
        {loading ? (
          <LoadingSpinner message="Loading your bookings..." />
        ) : bookings.length === 0 ? (
          <EmptyState
            title="No bookings found"
            message={
              scope || status
                ? 'No reservations matched your selected filters.'
                : 'You have not made any parking reservations yet.'
            }
            action={
              <Link to="/consumer/search" className="btn btn-primary btn-sm">
                Search Parking Lots
              </Link>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Parking Facility</th>
                    <th>Slot</th>
                    <th>Vehicle</th>
                    <th>Start Time</th>
                    <th>End Time</th>
                    <th>Effective Status</th>
                    <th>Amount</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {bookings.map((b) => (
                    <tr key={b.id}>
                      <td className="font-mono font-semibold">{b.reference}</td>
                      <td>
                        <strong>{b.lot_name}</strong>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>{b.lot_code}</div>
                      </td>
                      <td>Slot {b.slot_number}</td>
                      <td className="font-mono">{b.vehicle_plate}</td>
                      <td>{formatDateTime(b.start_time)}</td>
                      <td>{formatDateTime(b.end_time)}</td>
                      <td>
                        <BookingStatusBadge status={b.effective_status as BookingStatus} />
                      </td>
                      <td className="font-semibold">{formatMoney(b.base_amount)}</td>
                      <td>
                        <Link to={`/consumer/bookings/${b.id}`} className="btn btn-outline btn-sm">
                          Details →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={page}
              totalPages={totalPages}
              totalItems={count}
              pageSize={pageSize}
              onPageChange={setPage}
              loading={loading}
            />
          </>
        )}
      </Card>
    </div>
  )
}

