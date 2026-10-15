// Booking Confirmation Page
import React, { useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import type { ConsumerBookingDetail, PaymentReceipt } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { BookingStatusBadge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { Modal } from '../../components/common/Modal'
import { formatMoney, formatDateTime } from '../../lib/format'

export const BookingConfirmationPage: React.FC = () => {
  const { bookingId } = useParams<{ bookingId: string }>()
  const [searchParams] = useSearchParams()
  const paymentId = searchParams.get('payment')

  const [receipt, setReceipt] = useState<PaymentReceipt | null>(null)
  const [loadingReceipt, setLoadingReceipt] = useState(false)
  const [showReceiptModal, setShowReceiptModal] = useState(false)
  const [receiptError, setReceiptError] = useState<string | null>(null)

  const {
    data: booking,
    loading: loadingBooking,
    error: errorBooking,
    refetch,
  } = useApi<ConsumerBookingDetail>(bookingId ? `/bookings/${bookingId}/` : null)

  const { data: autoReceipt } = useApi<PaymentReceipt>(paymentId ? `/payments/${paymentId}/receipt/` : null)

  const handleDownloadReceipt = async () => {
    if (autoReceipt) {
      setReceipt(autoReceipt)
      setShowReceiptModal(true)
      return
    }
    if (!paymentId) return
    setLoadingReceipt(true)
    setReceiptError(null)

    try {
      const res = await apiFetch<PaymentReceipt>(`/payments/${paymentId}/receipt/`)
      setReceipt(res)
      setShowReceiptModal(true)
    } catch {
      setReceiptError('Receipt is not yet available for download.')
    } finally {
      setLoadingReceipt(false)
    }
  }

  if (loadingBooking) return <LoadingSpinner message="Confirming reservation..." />
  if (errorBooking || !booking) {
    return <ErrorState error={errorBooking} title="Booking not found" onRetry={refetch} />
  }

  return (
    <div className="checkout-panel">
      <div className="success-hero">
        <div className="success-mark">
          <Icon name="check" size={30} />
        </div>
        <h1 className="page-title">Booking confirmed</h1>
        <p className="page-subtitle">Your slot is reserved and ready for your arrival</p>
      </div>

      <Card>
        {/* Gate Pass / Reference */}
        <div className="gate-pass">
          <span className="gate-pass-label">Gate pass · booking reference</span>
          <div className="gate-pass-ref">{booking.reference}</div>
          <div className="badge-row" style={{ justifyContent: 'center' }}>
            <BookingStatusBadge status={booking.effective_status} />
            <span className="muted-sm">Show this code at the lot gate</span>
          </div>
        </div>

        {/* Booking details */}
        <div className="info-list">
          <div className="info-row">
            <span className="info-label">Parking facility</span>
            <span className="info-value">{booking.lot_name}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Facility address</span>
            <span className="info-value">
              {booking.lot_address_line}, {booking.lot_city}
            </span>
          </div>
          <div className="info-row">
            <span className="info-label">Assigned slot</span>
            <span className="info-value">
              Slot {booking.slot_number} (Floor {booking.slot_floor})
            </span>
          </div>
          <div className="info-row">
            <span className="info-label">Vehicle plate</span>
            <span className="info-value font-mono">{booking.vehicle_plate}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Start time</span>
            <span className="info-value">{formatDateTime(booking.start_time)}</span>
          </div>
          <div className="info-row">
            <span className="info-label">End time</span>
            <span className="info-value">{formatDateTime(booking.end_time)}</span>
          </div>
        </div>

        <div className="amount-line">
          <span className="amount-label">Total paid</span>
          <span className="amount-value text-success">
            {formatMoney(autoReceipt?.amount ?? booking.base_amount)}
          </span>
        </div>

        {receiptError && (
          <p className="text-danger mt-2" style={{ fontSize: '0.875rem' }}>
            {receiptError}
          </p>
        )}

        <div className="toolbar mt-4">
          {paymentId && (
            <Button variant="outline" loading={loadingReceipt} onClick={handleDownloadReceipt}>
              <Icon name="receipt" size={16} /> View tax receipt
            </Button>
          )}

          <Link to={`/consumer/bookings/${booking.id}`} className="btn btn-secondary btn-md">
            Manage booking
          </Link>

          <Link to="/consumer" className="btn btn-primary btn-md" style={{ marginLeft: 'auto' }}>
            Go to dashboard <Icon name="arrowRight" size={15} />
          </Link>
        </div>
      </Card>

      {/* Printable Receipt Modal */}
      <Modal
        isOpen={showReceiptModal}
        title="Payment tax receipt"
        onClose={() => setShowReceiptModal(false)}
        footer={
          <Button variant="secondary" onClick={() => setShowReceiptModal(false)}>
            Close
          </Button>
        }
      >
        {receipt && (
          <div style={{ fontSize: '0.875rem' }}>
            <div className="receipt-head">
              <h4 style={{ fontSize: '1.125rem', fontWeight: 700 }}>SPMS Parking Receipt</h4>
              <p className="text-muted font-mono">{receipt.receipt_number}</p>
            </div>

            <div className="info-list">
              <div className="info-row">
                <span className="info-label">Booking reference</span>
                <span className="info-value font-mono">{receipt.booking_reference}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Facility</span>
                <span className="info-value">{receipt.lot_name}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Slot</span>
                <span className="info-value">{receipt.slot_number}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Duration</span>
                <span className="info-value">{receipt.billed_hours} hrs</span>
              </div>
              <div className="info-row">
                <span className="info-label">Payment date</span>
                <span className="info-value">{formatDateTime(receipt.paid_at)}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Payment method</span>
                <span className="info-value">{receipt.method}</span>
              </div>
            </div>

            <div className="amount-line">
              <span className="amount-label">Amount paid</span>
              <span className="amount-value text-success">{formatMoney(receipt.amount)}</span>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}