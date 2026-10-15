// Consumer Booking Details Page (Cancellation and Extension flows)
import React, { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ConsumerBookingDetail, ExtensionQuote } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { BookingStatusBadge } from '../../components/common/Badge'
import { Modal } from '../../components/common/Modal'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatMoney, formatDateTime, toDatetimeLocalValue } from '../../lib/format'

export const BookingDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const {
    data: booking,
    loading,
    error,
    refetch,
  } = useApi<ConsumerBookingDetail>(id ? `/bookings/${id}/` : null)

  // Cancellation State
  const [showCancelModal, setShowCancelModal] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  // Extension State
  const [showExtendModal, setShowExtendModal] = useState(false)
  const [newEndTime, setNewEndTime] = useState('')
  const [quote, setQuote] = useState<ExtensionQuote | null>(null)
  const [loadingQuote, setLoadingQuote] = useState(false)
  const [quoteError, setQuoteError] = useState<string | null>(null)

  const handleCancel = async () => {
    if (!id) return
    setCancelling(true)
    setCancelError(null)

    try {
      await apiFetch(`/bookings/${id}/cancel/`, { method: 'POST' })
      setShowCancelModal(false)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        setCancelError(getFriendlyErrorMessage(err))
      } else {
        setCancelError('Failed to cancel booking.')
      }
    } finally {
      setCancelling(false)
    }
  }

  const handleRequestQuote = async (endVal: string) => {
    if (!id || !endVal) return
    setLoadingQuote(true)
    setQuoteError(null)
    setQuote(null)

    try {
      const endIso = new Date(endVal).toISOString()
      const res = await apiFetch<ExtensionQuote>(
        `/bookings/${id}/extension-quote/?end_time=${encodeURIComponent(endIso)}`
      )
      setQuote(res)
    } catch (err) {
      if (err instanceof ApiError) {
        setQuoteError(getFriendlyErrorMessage(err))
      } else {
        setQuoteError('Failed to calculate extension quote.')
      }
    } finally {
      setLoadingQuote(false)
    }
  }

  const handleProceedToExtensionPayment = () => {
    if (!id || !quote) return
    navigate(`/consumer/payment/${id}?purpose=EXTENSION&end_time=${encodeURIComponent(quote.new_end_time)}&amount=${encodeURIComponent(quote.extension_amount)}`)
  }

  const openExtendDialog = () => {
    if (booking) {
      const currentEnd = new Date(booking.end_time)
      currentEnd.setHours(currentEnd.getHours() + 1)
      const defaultNext = toDatetimeLocalValue(currentEnd)
      setNewEndTime(defaultNext)
      handleRequestQuote(defaultNext)
    }
    setShowExtendModal(true)
  }

  if (loading) return <LoadingSpinner message="Loading reservation details..." />
  if (error || !booking) {
    return <ErrorState error={error} title="Booking not found" onRetry={refetch} />
  }

  return (
    <div>
      <div className="mb-2">
        <Link to="/consumer/bookings" className="text-muted" style={{ fontSize: '0.875rem' }}>
          ← Back to My Bookings
        </Link>
      </div>

      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h1 className="page-title font-mono">{booking.reference}</h1>
            <BookingStatusBadge status={booking.effective_status} />
          </div>
          <p className="page-subtitle">
            {booking.lot_name} · Slot {booking.slot_number} (Floor {booking.slot_floor})
          </p>
        </div>

        <div className="page-actions">
          {booking.effective_status === 'PENDING_PAYMENT' && (
            <Link to={`/consumer/payment/${booking.id}`} className="btn btn-primary">
              Pay Now →
            </Link>
          )}

          {booking.can_extend && (
            <Button variant="secondary" onClick={openExtendDialog}>
              Extend Parking Window
            </Button>
          )}

          {booking.can_cancel && (
            <Button variant="danger" onClick={() => setShowCancelModal(true)}>
              Cancel Reservation
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2">
        {/* Main Details */}
        <Card title="Reservation Info">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div className="flex justify-between">
              <span className="text-muted">Facility</span>
              <span className="font-semibold">{booking.lot_name} ({booking.lot_code})</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Address</span>
              <span>{booking.lot_address_line}, {booking.lot_city}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Vehicle License Plate</span>
              <span className="font-mono font-semibold">{booking.vehicle_plate}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Scheduled Arrival</span>
              <span>{formatDateTime(booking.start_time)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Scheduled Departure</span>
              <span>{formatDateTime(booking.end_time)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Total Billed Duration</span>
              <span>{booking.billed_hours} hours</span>
            </div>
            <div className="flex justify-between" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.5rem' }}>
              <span className="font-semibold">Base Price</span>
              <span className="font-semibold">{formatMoney(booking.base_amount)}</span>
            </div>
          </div>
        </Card>

        {/* Live Session & Financials */}
        <Card title="Session Activity & Financials">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div className="flex justify-between">
              <span className="text-muted">Actual Check-in</span>
              <span>{booking.actual_entry_at ? formatDateTime(booking.actual_entry_at) : 'Not checked in yet'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted">Actual Check-out</span>
              <span>{booking.actual_exit_at ? formatDateTime(booking.actual_exit_at) : 'Not checked out'}</span>
            </div>

            {booking.cancelled_at && (
              <div className="flex justify-between" style={{ color: 'var(--danger)' }}>
                <span>Cancelled At</span>
                <span>{formatDateTime(booking.cancelled_at)}</span>
              </div>
            )}

            {booking.refund_due_amount && Number(booking.refund_due_amount) > 0 && (
              <div className="flex justify-between" style={{ color: 'var(--success)', fontWeight: 600 }}>
                <span>Refund Due / Processed</span>
                <span>{formatMoney(booking.refund_due_amount)}</span>
              </div>
            )}

            {booking.overstay_hours > 0 && (
              <div
                style={{
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '4px',
                  padding: '0.75rem',
                  marginTop: '0.5rem',
                }}
              >
                <div style={{ fontWeight: 600, color: '#991b1b', marginBottom: '0.25rem' }}>Overstay Recorded</div>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem' }}>
                  <span>Overstay Duration:</span>
                  <span>{booking.overstay_hours} hours</span>
                </div>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem', fontWeight: 600, marginTop: '0.25rem' }}>
                  <span>Recorded Fee:</span>
                  <span>{formatMoney(booking.overstay_amount)}</span>
                </div>
              </div>
            )}

            <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '4px', border: '1px solid #e2e8f0', marginTop: '0.5rem' }}>
              <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                Rates are charged per tariff schedule ({formatMoney(booking.hourly_rate)}/hr).
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Cancel Modal */}
      <Modal
        isOpen={showCancelModal}
        title="Cancel Parking Reservation"
        onClose={() => setShowCancelModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCancelModal(false)}>
              Keep Reservation
            </Button>
            <Button variant="danger" loading={cancelling} onClick={handleCancel}>
              Confirm Cancellation
            </Button>
          </>
        }
      >
        <p style={{ marginBottom: '1rem' }}>
          Are you sure you want to cancel booking <strong>{booking.reference}</strong>?
        </p>
        <p className="text-muted" style={{ fontSize: '0.875rem' }}>
          If cancelled before the system cutoff window, any eligible refund will be queued automatically.
        </p>
        {cancelError && <p className="text-danger mt-2">{cancelError}</p>}
      </Modal>

      {/* Extend Modal */}
      <Modal
        isOpen={showExtendModal}
        title="Extend Parking Window"
        onClose={() => setShowExtendModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowExtendModal(false)}>
              Close
            </Button>
            <Button
              variant="primary"
              disabled={!quote || loadingQuote}
              onClick={handleProceedToExtensionPayment}
            >
              Pay & Confirm Extension
            </Button>
          </>
        }
      >
        <div className="form-group">
          <label className="form-label" htmlFor="newEnd">
            Select New End Time
          </label>
          <input
            id="newEnd"
            type="datetime-local"
            className="form-control"
            value={newEndTime}
            onChange={(e) => {
              setNewEndTime(e.target.value)
              handleRequestQuote(e.target.value)
            }}
          />
        </div>

        {loadingQuote && <LoadingSpinner size="sm" message="Calculating quote..." />}
        {quoteError && <p className="text-danger mt-2" style={{ fontSize: '0.875rem' }}>{quoteError}</p>}

        {quote && (
          <div style={{ background: '#f0f9ff', border: '1px solid #bae6fd', padding: '0.85rem', borderRadius: '4px', marginTop: '1rem' }}>
            <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#0369a1', marginBottom: '0.5rem' }}>Extension Quote</h4>
            <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
              <span>Additional Time:</span>
              <span>{quote.added_hours} hrs</span>
            </div>
            <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
              <span>Extension Fee:</span>
              <span className="font-semibold">{formatMoney(quote.extension_amount)}</span>
            </div>
            <div className="flex justify-between" style={{ fontSize: '0.8125rem', borderTop: '1px solid #bae6fd', paddingTop: '0.35rem', fontWeight: 700 }}>
              <span>New Total Amount:</span>
              <span>{formatMoney(quote.new_base_amount)}</span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

