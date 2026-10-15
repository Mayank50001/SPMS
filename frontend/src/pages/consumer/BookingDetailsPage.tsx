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
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
    navigate(
      `/consumer/payment/${id}?purpose=EXTENSION&end_time=${encodeURIComponent(quote.new_end_time)}&amount=${encodeURIComponent(quote.extension_amount)}`
    )
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
      <Link to="/consumer/bookings" className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to my bookings
      </Link>

      <PageHeader
        eyebrow="Booking details"
        title={<span className="font-mono">{booking.reference}</span>}
        subtitle={
          <span className="badge-row">
            <BookingStatusBadge status={booking.effective_status} />
            <span>
              {booking.lot_name} · Slot {booking.slot_number} (Floor {booking.slot_floor})
            </span>
          </span>
        }
        actions={
          <>
            {booking.effective_status === 'PENDING_PAYMENT' && (
              <Link to={`/consumer/payment/${booking.id}`} className="btn btn-primary btn-md">
                <Icon name="wallet" size={16} /> Pay now
              </Link>
            )}

            {booking.can_extend && (
              <Button variant="secondary" onClick={openExtendDialog}>
                <Icon name="clock" size={16} /> Extend window
              </Button>
            )}

            {booking.can_cancel && (
              <Button variant="danger" onClick={() => setShowCancelModal(true)}>
                <Icon name="close" size={16} /> Cancel reservation
              </Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-2">
        {/* Main Details */}
        <Card title="Reservation info" subtitle="What you booked">
          <div className="info-list">
            <div className="info-row">
              <span className="info-label">Facility</span>
              <span className="info-value">
                {booking.lot_name} ({booking.lot_code})
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">Address</span>
              <span className="info-value">
                {booking.lot_address_line}, {booking.lot_city}
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">Vehicle plate</span>
              <span className="info-value font-mono">{booking.vehicle_plate}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Scheduled arrival</span>
              <span className="info-value">{formatDateTime(booking.start_time)}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Scheduled departure</span>
              <span className="info-value">{formatDateTime(booking.end_time)}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Billed duration</span>
              <span className="info-value">{booking.billed_hours} hours</span>
            </div>
            <div className="info-row">
              <span className="info-label font-semibold">Base price</span>
              <span className="info-value">{formatMoney(booking.base_amount)}</span>
            </div>
          </div>
        </Card>

        {/* Live Session & Financials */}
        <Card title="Session & financials" subtitle="Check-in, check-out and charges">
          <div className="info-list">
            <div className="info-row">
              <span className="info-label">Actual check-in</span>
              <span className="info-value">
                {booking.actual_entry_at ? formatDateTime(booking.actual_entry_at) : 'Not checked in yet'}
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">Actual check-out</span>
              <span className="info-value">
                {booking.actual_exit_at ? formatDateTime(booking.actual_exit_at) : 'Not checked out'}
              </span>
            </div>

            {booking.cancelled_at && (
              <div className="info-row">
                <span className="info-label text-danger">Cancelled at</span>
                <span className="info-value text-danger">{formatDateTime(booking.cancelled_at)}</span>
              </div>
            )}

            {booking.refund_due_amount && Number(booking.refund_due_amount) > 0 && (
              <div className="info-row">
                <span className="info-label text-success">Refund due / processed</span>
                <span className="info-value text-success">
                  {formatMoney(booking.refund_due_amount)}
                </span>
              </div>
            )}
          </div>

          {booking.overstay_hours > 0 && (
            <div className="alert alert-danger mt-3">
              <span className="alert-icon text-danger">
                <Icon name="alert" size={18} />
              </span>
              <div className="alert-body">
                <p className="alert-title">Overstay recorded</p>
                <div className="row-between">
                  <span>Overstay duration</span>
                  <span className="font-semibold">{booking.overstay_hours} hours</span>
                </div>
                <div className="row-between">
                  <span>Recorded fee</span>
                  <span className="font-semibold">{formatMoney(booking.overstay_amount)}</span>
                </div>
              </div>
            </div>
          )}

          <div className="alert alert-info mb-0">
            <span className="alert-icon text-primary">
              <Icon name="info" size={18} />
            </span>
            <div className="alert-body">
              <p>
                Rates are charged per tariff schedule ({formatMoney(booking.hourly_rate)}/hr).
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Cancel Modal */}
      <Modal
        isOpen={showCancelModal}
        title="Cancel parking reservation"
        onClose={() => setShowCancelModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCancelModal(false)}>
              Keep reservation
            </Button>
            <Button variant="danger" loading={cancelling} onClick={handleCancel}>
              Confirm cancellation
            </Button>
          </>
        }
      >
        <p style={{ marginBottom: '1rem' }}>
          Are you sure you want to cancel booking <strong>{booking.reference}</strong>?
        </p>
        <p className="text-muted" style={{ fontSize: '0.875rem' }}>
          If cancelled before the system cutoff window, any eligible refund will be queued
          automatically.
        </p>
        {cancelError && <p className="text-danger mt-2">{cancelError}</p>}
      </Modal>

      {/* Extend Modal */}
      <Modal
        isOpen={showExtendModal}
        title="Extend parking window"
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
              Pay &amp; confirm extension
            </Button>
          </>
        }
      >
        <div className="form-group">
          <label className="form-label" htmlFor="newEnd">
            Select new end time
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
        {quoteError && (
          <p className="text-danger mt-2" style={{ fontSize: '0.875rem' }}>
            {quoteError}
          </p>
        )}

        {quote && (
          <div className="quote-box">
            <h4 className="quote-title">Extension quote</h4>
            <div className="row-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
              <span>Additional time</span>
              <span>{quote.added_hours} hrs</span>
            </div>
            <div className="row-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
              <span>Extension fee</span>
              <span className="font-semibold">{formatMoney(quote.extension_amount)}</span>
            </div>
            <div className="amount-line" style={{ marginTop: '0.5rem', paddingTop: '0.5rem' }}>
              <span className="amount-label">New total</span>
              <span className="amount-value text-primary">{formatMoney(quote.new_base_amount)}</span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}