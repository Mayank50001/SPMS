// Payment Checkout & Confirmation Page (D83)
import React, { useState, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ConsumerBookingDetail, PaymentInitiationResponse, ExtensionQuote } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatMoney, formatDateTime } from '../../lib/format'

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Razorpay?: any
  }
}

export const PaymentPage: React.FC = () => {
  const { bookingId } = useParams<{ bookingId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const purpose = (searchParams.get('purpose') as 'BOOKING' | 'EXTENSION') || 'BOOKING'
  const extensionEndTime = searchParams.get('end_time') || undefined
  const extensionAmountParam = searchParams.get('amount') || undefined

  const [paymentInitiation, setPaymentInitiation] = useState<PaymentInitiationResponse | null>(null)
  const [initiating, setInitiating] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scriptLoaded, setScriptLoaded] = useState(() => typeof window !== 'undefined' && !!window.Razorpay)

  // The backend tells us which gateway minted this order: mock orders return
  // client_payload.gateway === "mock" (D83), real Razorpay orders "razorpay".
  const isMockGateway = paymentInitiation?.client_payload?.gateway === 'mock'

  // Fetch booking details
  const {
    data: booking,
    loading: loadingBooking,
    error: errorBooking,
  } = useApi<ConsumerBookingDetail>(bookingId ? `/bookings/${bookingId}/` : null)

  // Fetch quote if extension without amount in search params
  const { data: extensionQuote } = useApi<ExtensionQuote>(
    purpose === 'EXTENSION' && extensionEndTime && !extensionAmountParam && bookingId
      ? `/bookings/${bookingId}/extension-quote/?end_time=${encodeURIComponent(extensionEndTime)}`
      : null
  )

  // Dynamically load Razorpay checkout script if not present
  useEffect(() => {
    if (window.Razorpay) return
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.async = true
    script.onload = () => setScriptLoaded(true)
    script.onerror = () => setScriptLoaded(false)
    document.body.appendChild(script)
  }, [])

  // Initiate payment attempt
  const handleInitiatePayment = async () => {
    if (!bookingId) return
    setInitiating(true)
    setError(null)

    try {
      const payload: Record<string, unknown> = {
        booking: Number(bookingId),
        purpose,
      }
      if (purpose === 'EXTENSION' && extensionEndTime) {
        payload.end_time = extensionEndTime
      }

      const res = await apiFetch<PaymentInitiationResponse>('/payments/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })

      setPaymentInitiation(res)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to initialize payment gateway.')
      }
    } finally {
      setInitiating(false)
    }
  }

  // Handle gateway return and server verification
  const handleConfirmPayment = async (gatewayPayload: Record<string, unknown>) => {
    if (!paymentInitiation) return
    setConfirming(true)
    setError(null)

    try {
      await apiFetch(`/payments/${paymentInitiation.id}/confirm/`, {
        method: 'POST',
        body: JSON.stringify({ payload: gatewayPayload }),
      })

      // Extension payments return to booking details; new bookings go to the confirmation page (Bug 1B fix)
      if (purpose === 'EXTENSION') {
        navigate(`/consumer/bookings/${bookingId}`)
      } else {
        navigate(`/consumer/confirmation/${bookingId}?payment=${paymentInitiation.id}`)
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Payment verification failed. Please check your bank or contact support.')
      }
    } finally {
      setConfirming(false)
    }
  }

  // Trigger Razorpay modal
  const openRazorpayCheckout = () => {
    if (!paymentInitiation || !paymentInitiation.client_payload) {
      setError('Payment payload unavailable.')
      return
    }

    if (window.Razorpay) {
      const options = {
        ...paymentInitiation.client_payload,
        handler: (response: Record<string, unknown>) => {
          handleConfirmPayment(response)
        },
        modal: {
          ondismiss: () => {
            // User closed the modal
          },
        },
      }
      const rzp = new window.Razorpay(options)
      rzp.open()
    } else {
      // Razorpay Checkout script is required for the real gateway (D83);
      // never fall back to confirming without a gateway callback.
      setError('Secure checkout is unavailable. Please refresh the page and try again.')
    }
  }

  if (loadingBooking) return <LoadingSpinner message="Loading reservation details..." />
  if (errorBooking || !booking) {
    return <ErrorState error={errorBooking} title="Reservation not found" />
  }

  return (
    <div style={{ maxWidth: '640px', margin: '0 auto' }}>
      <div className="mb-2">
        <Link to={`/consumer/bookings/${booking.id}`} className="text-muted" style={{ fontSize: '0.875rem' }}>
          ← View Booking
        </Link>
      </div>

      <div className="page-header">
        <div>
          <h1 className="page-title">
            {purpose === 'EXTENSION' ? 'Pay for Extension' : 'Complete Payment'}
          </h1>
          <p className="page-subtitle">
            Reference: <span className="font-mono font-semibold">{booking.reference}</span>
          </p>
        </div>
      </div>

      {error && (
        <div className="error-state mb-4" role="alert">
          <div className="error-icon">⚠️</div>
          <div className="error-content">
            <h4 className="error-title">Payment Issue</h4>
            <p className="error-message">{error}</p>
          </div>
        </div>
      )}

      <Card title="Order Summary">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.25rem' }}>
          <div className="flex justify-between">
            <span className="text-muted">Parking Lot</span>
            <span className="font-semibold">{booking.lot_name}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Reserved Slot</span>
            <span className="font-semibold">Slot {booking.slot_number}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Vehicle</span>
            <span>{booking.vehicle_plate}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Window Start</span>
            <span>{formatDateTime(booking.start_time)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Window End</span>
            <span>{formatDateTime(purpose === 'EXTENSION' && extensionEndTime ? extensionEndTime : booking.end_time)}</span>
          </div>
          <div className="flex justify-between" style={{ borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
            <span style={{ fontSize: '1.125rem', fontWeight: 600 }}>Amount Due</span>
            <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--primary)' }}>
              {paymentInitiation
                ? formatMoney(paymentInitiation.amount)
                : purpose === 'EXTENSION'
                ? (extensionAmountParam || extensionQuote?.extension_amount
                    ? formatMoney(extensionAmountParam || extensionQuote!.extension_amount)
                    : 'Calculating...')
                : formatMoney(booking.base_amount)}
            </span>
          </div>
        </div>

        {booking.hold_expires_at && (
          <div className="mb-4 p-3" style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '4px' }}>
            <span className="badge badge-warning" style={{ marginBottom: '0.25rem' }}>Temporary Hold</span>
            <p style={{ fontSize: '0.8125rem', color: '#92400e' }}>
              Your slot is reserved until <strong>{formatDateTime(booking.hold_expires_at)}</strong>. Please complete payment before this time.
            </p>
          </div>
        )}

        {!paymentInitiation ? (
          <Button
            variant="primary"
            size="lg"
            className="w-100"
            style={{ width: '100%' }}
            loading={initiating}
            onClick={handleInitiatePayment}
          >
            Initiate Secure Checkout →
          </Button>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {isMockGateway ? (
              /* Test Mode / Mock Gateway Confirmation Helper (D83: only for PAYMENT_GATEWAY=mock) */
              <div style={{ border: '1px dashed #cbd5e1', borderRadius: '6px', padding: '1rem' }}>
                <div style={{ fontSize: '0.8125rem', color: '#64748b', marginBottom: '0.5rem', textAlign: 'center' }}>
                  Test Mode / Gateway Mock Simulation
                </div>
                <Button
                  variant="secondary"
                  size="md"
                  className="w-100"
                  style={{ width: '100%' }}
                  loading={confirming}
                  onClick={() =>
                    handleConfirmPayment(
                      paymentInitiation.client_payload || { mock: true, order_id: paymentInitiation.provider_order_id }
                    )
                  }
                >
                  Complete Test Payment (Simulate Gateway Confirmation)
                </Button>
              </div>
            ) : scriptLoaded && window.Razorpay ? (
              <Button
                variant="primary"
                size="lg"
                className="w-100"
                style={{ width: '100%' }}
                loading={confirming}
                onClick={openRazorpayCheckout}
              >
                Pay with Razorpay ({formatMoney(paymentInitiation.amount)})
              </Button>
            ) : (
              <div className="error-state" role="alert">
                <div className="error-icon">⚠️</div>
                <div className="error-content">
                  <h4 className="error-title">Payment gateway unavailable</h4>
                  <p className="error-message">
                    We couldn't load the secure checkout. Check your connection and refresh to try again.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}

