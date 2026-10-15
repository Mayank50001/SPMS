// Operator Bookings Management Page (Check-in & Check-out actions)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { OperatorBookingRow, ParkingLot, BookingStatus } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { BookingStatusBadge } from '../../components/common/Badge'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { formatMoney, formatDateTime } from '../../lib/format'

export const ManagerBookingsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const lotParam = searchParams.get('lot') || ''
  const scopeParam = searchParams.get('scope') || ''
  const statusParam = searchParams.get('status') || ''

  const [lotFilter, setLotFilter] = useState(lotParam)
  const [scopeFilter, setScopeFilter] = useState(scopeParam)
  const [statusFilter, setStatusFilter] = useState(statusParam)

  // Fetch operator's assigned lots for filter dropdown
  const { results: lots } = usePaginated<ParkingLot>('/parking-lots/', { pageSize: 100 })

  // Fetch operator booking rows
  const {
    results: bookings,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<OperatorBookingRow>('/bookings/', {
    params: {
      lot: lotParam || undefined,
      scope: scopeParam || undefined,
      status: statusParam || undefined,
      ordering: '-start_time',
    },
  })

  // Action states
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const handleFilterChange = (newLot: string, newScope: string, newStatus: string) => {
    const sp = new URLSearchParams()
    if (newLot) sp.set('lot', newLot)
    if (newScope) sp.set('scope', newScope)
    if (newStatus) sp.set('status', newStatus)
    setSearchParams(sp)
  }

  const handleCheckIn = async (b: OperatorBookingRow) => {
    setActionLoadingId(b.id)
    setActionError(null)
    try {
      await apiFetch<OperatorBookingRow>(`/bookings/${b.id}/check-in/`, {
        method: 'POST',
      })
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(getFriendlyErrorMessage(err))
      } else {
        setActionError('Failed to process check-in.')
      }
    } finally {
      setActionLoadingId(null)
    }
  }

  const handleCheckOut = async (b: OperatorBookingRow) => {
    setActionLoadingId(b.id)
    setActionError(null)
    try {
      await apiFetch<OperatorBookingRow>(`/bookings/${b.id}/check-out/`, {
        method: 'POST',
      })
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(getFriendlyErrorMessage(err))
      } else {
        setActionError('Failed to process check-out.')
      }
    } finally {
      setActionLoadingId(null)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Operations Bookings & Gate Control</h1>
          <p className="page-subtitle">Process vehicle check-ins, departures, and monitor overstays</p>
        </div>
      </div>

      {actionError && (
        <div className="error-state mb-4" role="alert">
          <div className="error-icon">⚠️</div>
          <div className="error-content">
            <h4 className="error-title">Action Refused</h4>
            <p className="error-message">{actionError}</p>
          </div>
        </div>
      )}

      {/* Filter Bar */}
      <div className="filter-bar">
        <div style={{ minWidth: '180px' }}>
          <select
            className="form-control"
            value={lotFilter}
            onChange={(e) => {
              setLotFilter(e.target.value)
              handleFilterChange(e.target.value, scopeFilter, statusFilter)
            }}
          >
            <option value="">All Assigned Facilities</option>
            {lots.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.code})
              </option>
            ))}
          </select>
        </div>

        <div style={{ minWidth: '140px' }}>
          <select
            className="form-control"
            value={scopeFilter}
            onChange={(e) => {
              setScopeFilter(e.target.value)
              handleFilterChange(lotFilter, e.target.value, statusFilter)
            }}
          >
            <option value="">All Time Scopes</option>
            <option value="upcoming">Upcoming</option>
            <option value="ongoing">Ongoing (Active in Lot)</option>
            <option value="past">Past</option>
          </select>
        </div>

        <div style={{ minWidth: '140px' }}>
          <select
            className="form-control"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              handleFilterChange(lotFilter, scopeFilter, e.target.value)
            }}
          >
            <option value="">All Statuses</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="COMPLETED">Completed</option>
            <option value="PENDING_PAYMENT">Pending Payment</option>
            <option value="CANCELLED">Cancelled</option>
            <option value="EXPIRED">Expired</option>
          </select>
        </div>

        {(lotFilter || scopeFilter || statusFilter) && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setLotFilter('')
              setScopeFilter('')
              setStatusFilter('')
              setSearchParams({})
            }}
          >
            Reset Filters
          </Button>
        )}
      </div>

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading operator bookings..." />
        ) : bookings.length === 0 ? (
          <EmptyState
            title="No bookings found"
            message="No reservations match the selected facility or filters."
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Customer</th>
                    <th>Vehicle</th>
                    <th>Facility & Slot</th>
                    <th>Window</th>
                    <th>Status</th>
                    <th>Financials</th>
                    <th>Gate Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {bookings.map((b) => (
                    <tr key={b.id}>
                      <td>
                        <div className="font-mono font-semibold">{b.reference}</div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>#{b.id}</div>
                      </td>
                      <td>
                        <div>{b.consumer_name || 'Driver'}</div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>{b.consumer_email}</div>
                      </td>
                      <td>
                        <span className="font-mono font-semibold">{b.vehicle_plate}</span>
                      </td>
                      <td>
                        <div><strong>Slot {b.slot_number}</strong></div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>{b.lot_name}</div>
                      </td>
                      <td>
                        <div style={{ fontSize: '0.8125rem' }}>In: {formatDateTime(b.start_time)}</div>
                        <div style={{ fontSize: '0.8125rem' }}>Out: {formatDateTime(b.end_time)}</div>
                      </td>
                      <td>
                        <BookingStatusBadge status={b.effective_status as BookingStatus} />
                      </td>
                      <td>
                        <div>{formatMoney(b.base_amount)}</div>
                        {b.overstay_hours > 0 && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--danger)', fontWeight: 600 }}>
                            Overstay: {formatMoney(b.overstay_amount)} ({b.overstay_hours}h)
                          </div>
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.35rem' }}>
                          {b.can_check_in && (
                            <Button
                              variant="primary"
                              size="sm"
                              loading={actionLoadingId === b.id}
                              onClick={() => handleCheckIn(b)}
                            >
                              Check-In
                            </Button>
                          )}
                          {b.can_check_out && (
                            <Button
                              variant="secondary"
                              size="sm"
                              loading={actionLoadingId === b.id}
                              onClick={() => handleCheckOut(b)}
                            >
                              Check-Out
                            </Button>
                          )}
                          {!b.can_check_in && !b.can_check_out && (
                            <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                              No action
                            </span>
                          )}
                        </div>
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

