// Payment Checkout & Confirmation Page (D83)
import React, { useState, useEffect } from 'react'
import { useParams, useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ConsumerBookingDetail, PaymentInitiationResponse, ExtensionQuote } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
    <div className="checkout-panel">
      <Link to={`/consumer/bookings/${booking.id}`} className="link-back mb-3">
        <span aria-hidden="true">←</span> View booking
      </Link>

      <PageHeader
        eyebrow={purpose === 'EXTENSION' ? 'Step 2 of 2 · Extension' : 'Step 2 of 2 · Payment'}
        title={purpose === 'EXTENSION' ? 'Pay for your extension' : 'Complete your payment'}
        subtitle={
          <>
            Booking reference{' '}
            <span className="font-mono font-semibold">{booking.reference}</span>
          </>
        }
      />

      {error && (
        <div className="alert alert-danger" role="alert">
          <span className="alert-icon text-danger">
            <Icon name="alert" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Payment issue</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      <Card title="Order summary" subtitle="Confirm the details before you pay">
        <div className="info-list">
          <div className="info-row">
            <span className="info-label">Parking facility</span>
            <span className="info-value">{booking.lot_name}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Reserved slot</span>
            <span className="info-value">Slot {booking.slot_number}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Vehicle</span>
            <span className="info-value font-mono">{booking.vehicle_plate}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Window start</span>
            <span className="info-value">{formatDateTime(booking.start_time)}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Window end</span>
            <span className="info-value">
              {formatDateTime(
                purpose === 'EXTENSION' && extensionEndTime ? extensionEndTime : booking.end_time
              )}
            </span>
          </div>
        </div>

        <div className="amount-line">
          <span className="amount-label">Amount due</span>
          <span className="amount-value text-primary">
            {paymentInitiation
              ? formatMoney(paymentInitiation.amount)
              : purpose === 'EXTENSION'
              ? (extensionAmountParam || extensionQuote?.extension_amount
                  ? formatMoney(extensionAmountParam || extensionQuote!.extension_amount)
                  : 'Calculating...')
              : formatMoney(booking.base_amount)}
          </span>
        </div>

        {booking.hold_expires_at && (
          <div className="alert alert-warning mt-3" role="status">
            <span className="alert-icon">
              <Icon name="clock" size={18} />
            </span>
            <div className="alert-body">
              <p className="alert-title">Temporary hold</p>
              <p>
                Your slot is reserved until{' '}
                <strong>{formatDateTime(booking.hold_expires_at)}</strong>. Complete payment before
                this time or the slot is released.
              </p>
            </div>
          </div>
        )}

        {!paymentInitiation ? (
          <Button
            variant="primary"
            size="lg"
            className="w-100 mt-2"
            loading={initiating}
            onClick={handleInitiatePayment}
          >
            <Icon name="shield" size={16} /> Initiate secure checkout
          </Button>
        ) : (
          <div className="stack-sm mt-2">
            {isMockGateway ? (
              /* Test Mode / Mock Gateway Confirmation Helper (D83: only for PAYMENT_GATEWAY=mock) */
              <div className="mock-gateway">
                <p className="mock-gateway-label">Test mode · gateway simulation</p>
                <Button
                  variant="secondary"
                  size="md"
                  className="w-100"
                  loading={confirming}
                  onClick={() =>
                    handleConfirmPayment(
                      paymentInitiation.client_payload || {
                        mock: true,
                        order_id: paymentInitiation.provider_order_id,
                      }
                    )
                  }
                >
                  Complete test payment
                </Button>
              </div>
            ) : scriptLoaded && window.Razorpay ? (
              <Button
                variant="primary"
                size="lg"
                className="w-100"
                loading={confirming}
                onClick={openRazorpayCheckout}
              >
                <Icon name="shield" size={16} /> Pay with Razorpay (
                {formatMoney(paymentInitiation.amount)})
              </Button>
            ) : (
              <div className="alert alert-danger mb-0" role="alert">
                <span className="alert-icon text-danger">
                  <Icon name="alert" size={18} />
                </span>
                <div className="alert-body">
                  <p className="alert-title">Payment gateway unavailable</p>
                  <p>
                    We couldn't load the secure checkout. Check your connection and refresh to try
                    again.
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