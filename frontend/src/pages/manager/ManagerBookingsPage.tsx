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
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
      <PageHeader
        eyebrow="Gate operations"
        title="Bookings & gate control"
        subtitle="Process vehicle check-ins, departures, and monitor overstays"
        actions={
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <Icon name="refresh" size={15} /> Refresh
          </Button>
        }
      />

      {actionError && (
        <div className="alert alert-danger" role="alert">
          <span className="alert-icon text-danger">
            <Icon name="alert" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Action refused</p>
            <p>{actionError}</p>
          </div>
        </div>
      )}

      {/* Filter Bar */}
      <div className="filter-bar">
        <div style={{ minWidth: '200px' }}>
          <select
            className="form-control"
            value={lotFilter}
            onChange={(e) => {
              setLotFilter(e.target.value)
              handleFilterChange(e.target.value, scopeFilter, statusFilter)
            }}
          >
            <option value="">All assigned facilities</option>
            {lots.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.code})
              </option>
            ))}
          </select>
        </div>

        <div style={{ minWidth: '160px' }}>
          <select
            className="form-control"
            value={scopeFilter}
            onChange={(e) => {
              setScopeFilter(e.target.value)
              handleFilterChange(lotFilter, e.target.value, statusFilter)
            }}
          >
            <option value="">All time scopes</option>
            <option value="upcoming">Upcoming</option>
            <option value="ongoing">Ongoing (active in lot)</option>
            <option value="past">Past</option>
          </select>
        </div>

        <div style={{ minWidth: '160px' }}>
          <select
            className="form-control"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              handleFilterChange(lotFilter, scopeFilter, e.target.value)
            }}
          >
            <option value="">All statuses</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="IN_PROGRESS">In progress</option>
            <option value="COMPLETED">Completed</option>
            <option value="PENDING_PAYMENT">Pending payment</option>
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
            <Icon name="close" size={15} /> Reset filters
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
                    <th>Facility &amp; slot</th>
                    <th>Window</th>
                    <th>Status</th>
                    <th>Financials</th>
                    <th>Gate actions</th>
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
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                          {b.consumer_email}
                        </div>
                      </td>
                      <td>
                        <span className="plate">{b.vehicle_plate}</span>
                      </td>
                      <td>
                        <div>
                          <strong>Slot {b.slot_number}</strong>
                        </div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>{b.lot_name}</div>
                      </td>
                      <td style={{ fontSize: '0.8125rem' }}>
                        <div>In: {formatDateTime(b.start_time)}</div>
                        <div>Out: {formatDateTime(b.end_time)}</div>
                      </td>
                      <td>
                        <BookingStatusBadge status={b.effective_status as BookingStatus} />
                      </td>
                      <td>
                        <div>{formatMoney(b.base_amount)}</div>
                        {b.overstay_hours > 0 && (
                          <div
                            style={{ fontSize: '0.75rem', color: 'var(--danger)', fontWeight: 600 }}
                          >
                            Overstay {formatMoney(b.overstay_amount)} ({b.overstay_hours}h)
                          </div>
                        )}
                      </td>
                      <td>
                        <div className="toolbar" style={{ gap: '0.35rem' }}>
                          {b.can_check_in && (
                            <Button
                              variant="primary"
                              size="sm"
                              loading={actionLoadingId === b.id}
                              onClick={() => handleCheckIn(b)}
                            >
                              <Icon name="check" size={14} /> Check-in
                            </Button>
                          )}
                          {b.can_check_out && (
                            <Button
                              variant="secondary"
                              size="sm"
                              loading={actionLoadingId === b.id}
                              onClick={() => handleCheckOut(b)}
                            >
                              <Icon name="logout" size={14} /> Check-out
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