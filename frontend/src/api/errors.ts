// API Error Handling & translation

export interface ApiErrorResponse {
  error?: string
  message?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly fieldErrors?: Record<string, string[]>

  constructor(
    status: number,
    code?: string,
    fieldErrors?: Record<string, string[]>,
    message?: string,
  ) {
    super(message ?? code ?? `HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fieldErrors = fieldErrors
  }
}

const ERROR_CODE_MESSAGES: Record<string, string> = {
  BOOKING_CONFLICT: 'The selected slot has already been booked for this timeframe. Please choose a different slot or time window.',
  SLOT_UNAVAILABLE: 'This slot is currently unavailable for booking. Please pick another available slot.',
  MAX_DURATION_EXCEEDED: 'The selected booking duration exceeds the permitted limit for this slot or system policy.',
  MIN_DURATION_NOT_MET: 'The booking duration is below the minimum required duration.',
  INVALID_WINDOW: 'The chosen start and end time window is invalid. Please select an end time after the start time.',
  WINDOW_IN_PAST: 'The selected start time is in the past. Please choose a future window.',
  RATE_ABOVE_MAXIMUM: 'The specified hourly rate exceeds the maximum rate configured by system policy.',
  MAX_DURATION_ABOVE_CAP: 'The maximum duration exceeds the platform-wide cap.',
  MAX_RATE_BELOW_TARIFF: 'The maximum rate cannot be lowered below existing active tariffs in the system.',
  MAX_DURATION_BELOW_SLOT: 'The platform duration cap cannot be lowered below active slot durations.',
  LAST_ADMINISTRATOR: 'Action refused: Cannot demote or deactivate the last remaining Administrator.',
  PAYMENT_GATEWAY_UNAVAILABLE: 'The payment service is temporarily unavailable. Please try again shortly.',
  PAYMENT_NOT_PAYABLE: 'This booking is not in a payable state.',
  BOOKING_ALREADY_PAID: 'This booking has already been paid and confirmed.',
  PAYMENT_VERIFICATION_FAILED: 'Payment signature verification failed. Please contact support.',
  PAYMENT_CAPTURED_NOT_APPLIED: 'Payment succeeded with the gateway but could not be applied to the booking automatically.',
  PAYMENT_NOT_REFUNDABLE: 'This payment is not eligible for refund.',
  PAYMENT_REFUND_FAILED: 'The payment gateway could not process the refund. Please retry or contact support.',
  RECEIPT_NOT_AVAILABLE: 'Receipt is not available for this transaction.',
  BOOKING_NOT_CANCELLABLE: 'This booking cannot be cancelled in its current state.',
  BOOKING_NOT_CHECKINABLE: 'Check-in is only available for confirmed bookings that have arrived at the lot.',
  BOOKING_NOT_CHECKOUTABLE: 'Check-out is only available for bookings currently in progress.',
  SLOT_NOT_OCCUPIABLE: 'This slot cannot be physically occupied in its current state.',
  LOT_NOT_FOUND: 'The specified parking lot was not found or is not assigned to your account.',
  SLOT_NOT_FOUND: 'The specified parking slot was not found.',
  BOOKING_NOT_FOUND: 'The specified booking was not found.',
  PAYMENT_NOT_FOUND: 'The specified payment was not found.',
}

export function getFriendlyErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code && ERROR_CODE_MESSAGES[err.code]) {
      return ERROR_CODE_MESSAGES[err.code]
    }
    if (err.message && err.message !== err.code && !err.message.startsWith('HTTP ')) {
      return err.message
    }
    if (err.status === 401) {
      return 'Session expired or unauthenticated. Please log in.'
    }
    if (err.status === 403) {
      return 'You do not have permission to perform this action.'
    }
    if (err.status === 404) {
      return 'Requested resource was not found.'
    }
    if (err.status === 409) {
      return 'A conflict occurred. Please refresh and try again.'
    }
    if (err.status >= 500) {
      return 'A server error occurred. Please try again later.'
    }
  }
  if (err instanceof Error) {
    return err.message
  }
  return 'An unexpected error occurred.'
}

