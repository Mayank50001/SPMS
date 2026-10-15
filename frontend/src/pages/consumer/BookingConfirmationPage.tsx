// Booking Confirmation Page
import React, { useState } from 'react'
import { useParams, useSearchParams, Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import type { ConsumerBookingDetail, PaymentReceipt } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { BookingStatusBadge } from '../../components/common/Badge'
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
    <div style={{ maxWidth: '680px', margin: '0 auto' }}>
      <div className="text-center mb-4">
        <div style={{ fontSize: '3rem', marginBottom: '0.5rem' }}>🎉</div>
        <h1 className="page-title">Booking Confirmed!</h1>
        <p className="page-subtitle">Your parking slot is reserved and ready for your arrival</p>
      </div>

      <Card>
        {/* Pass / Reference Header */}
        <div
          style={{
            background: '#f8fafc',
            border: '2px dashed #cbd5e1',
            borderRadius: '8px',
            padding: '1.5rem',
            textAlign: 'center',
            marginBottom: '1.5rem',
          }}
        >
          <span className="text-muted" style={{ fontSize: '0.8125rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Gate Pass Booking Reference
          </span>
          <div className="font-mono" style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)', margin: '0.35rem 0' }}>
            {booking.reference}
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', alignItems: 'center' }}>
            <BookingStatusBadge status={booking.effective_status} />
            <span className="text-muted" style={{ fontSize: '0.8125rem' }}>· Show this code at lot gate</span>
          </div>
        </div>

        {/* Booking Details Grid */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', marginBottom: '1.5rem' }}>
          <div className="flex justify-between">
            <span className="text-muted">Parking Facility</span>
            <span className="font-semibold">{booking.lot_name}</span>
          </div>

          <div className="flex justify-between">
            <span className="text-muted">Facility Address</span>
            <span>{booking.lot_address_line}, {booking.lot_city}</span>
          </div>

          <div className="flex justify-between">
            <span className="text-muted">Assigned Slot</span>
            <span className="font-semibold">Slot {booking.slot_number} (Floor {booking.slot_floor})</span>
          </div>

          <div className="flex justify-between">
            <span className="text-muted">Vehicle License Plate</span>
            <span className="font-mono font-semibold">{booking.vehicle_plate}</span>
          </div>

          <div className="flex justify-between">
            <span className="text-muted">Start Time</span>
            <span>{formatDateTime(booking.start_time)}</span>
          </div>

          <div className="flex justify-between">
            <span className="text-muted">End Time</span>
            <span>{formatDateTime(booking.end_time)}</span>
          </div>

          <div className="flex justify-between" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
            <span style={{ fontSize: '1.125rem', fontWeight: 600 }}>Total Paid</span>
            <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--success)' }}>
              {formatMoney(autoReceipt?.amount ?? booking.base_amount)}
            </span>
          </div>
        </div>

        {receiptError && <p className="text-danger mb-2" style={{ fontSize: '0.875rem' }}>{receiptError}</p>}

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          {paymentId && (
            <Button
              variant="outline"
              loading={loadingReceipt}
              onClick={handleDownloadReceipt}
            >
              📄 View Tax Receipt
            </Button>
          )}

          <Link to={`/consumer/bookings/${booking.id}`} className="btn btn-secondary">
            Manage Booking
          </Link>

          <Link to="/consumer" className="btn btn-primary" style={{ marginLeft: 'auto' }}>
            Go to Dashboard →
          </Link>
        </div>
      </Card>

      {/* Printable Receipt Modal */}
      <Modal
        isOpen={showReceiptModal}
        title="Payment Tax Receipt"
        onClose={() => setShowReceiptModal(false)}
        footer={
          <Button variant="secondary" onClick={() => setShowReceiptModal(false)}>
            Close
          </Button>
        }
      >
        {receipt && (
          <div style={{ fontSize: '0.875rem' }}>
            <div style={{ textAlign: 'center', marginBottom: '1.25rem', borderBottom: '1px solid #e2e8f0', paddingBottom: '0.75rem' }}>
              <h4 style={{ fontSize: '1.125rem', fontWeight: 700 }}>SPMS Parking Receipt</h4>
              <p className="text-muted font-mono">{receipt.receipt_number}</p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div className="flex justify-between">
                <span className="text-muted">Booking Reference:</span>
                <span className="font-mono font-semibold">{receipt.booking_reference}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Facility:</span>
                <span>{receipt.lot_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Slot:</span>
                <span>{receipt.slot_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Duration:</span>
                <span>{receipt.billed_hours} hrs</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Payment Date:</span>
                <span>{formatDateTime(receipt.paid_at)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Payment Method:</span>
                <span>{receipt.method}</span>
              </div>
              <div className="flex justify-between" style={{ borderTop: '1px solid #e2e8f0', paddingTop: '0.5rem', fontWeight: 700 }}>
                <span>Amount Paid:</span>
                <span>{formatMoney(receipt.amount)}</span>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

