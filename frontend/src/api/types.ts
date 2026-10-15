// API Data Types — strictly mirroring docs/phase-9-frontend/API-MAP.md

export type UserRole = 'CONSUMER' | 'MANAGER' | 'ADMIN'

export interface User {
  id: number
  email: string
  full_name: string
  phone: string | null
  role: UserRole
  created_at: string
  is_active?: boolean
}

export interface AuthTokens {
  access: string
  refresh: string
  user: User
}

export interface RegisterResponse {
  id: number
  email: string
  full_name: string
  phone: string | null
}

export interface Vehicle {
  id: number
  registration_number: string
  state_code: string
  rto_code: string
  series: string
  unique_number: string
  make: string | null
  model: string | null
  color: string | null
  created_at: string
  updated_at: string
}

export interface VehicleCreatePayload {
  state_code: string
  rto_code: string
  series: string
  unique_number: string
  make?: string
  model?: string
  color?: string
}

export interface City {
  id: number
  code: string
  name: string
  created_at: string
}

export interface ParkingLot {
  id: number
  code: string
  name: string
  address_line: string
  city: City
  number: number
  state: string | null
  postal_code: string | null
  is_active: boolean
  manager: number | null
  created_at: string
  updated_at: string
}

export type SlotType = 'REGULAR' | 'COMPACT' | 'LARGE' | 'TWO_WHEELER' | 'EV'
export type PhysicalSlotStatus = 'AVAILABLE' | 'OCCUPIED' | 'OUT_OF_SERVICE'

export interface ParkingSlot {
  id: number
  lot: number
  lot_code: string
  number: string
  floor: number
  slot_type: SlotType
  status: PhysicalSlotStatus
  min_booking_hours: number
  max_booking_hours: number
  created_at: string
  updated_at: string
}

export interface Tariff {
  id: number
  lot: number
  lot_code: string
  slot_type: SlotType
  slot_type_label: string
  hourly_rate: string // Decimal string
  created_at: string
  updated_at: string
}

export interface BusinessRules {
  id: number
  max_hourly_rate: string
  max_booking_hours: number
  hold_minutes: number
  cancellation_cutoff_minutes: number
  overstay_multiplier: string
  overstay_grace_minutes: number
  updated_at: string
}

export type BookingStatus =
  | 'PENDING_PAYMENT'
  | 'CONFIRMED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'EXPIRED'
  | 'TERMINATED'

export interface ConsumerBooking {
  id: number
  reference: string
  status: BookingStatus
  effective_status: BookingStatus
  slot: number
  slot_number: string
  lot_code: string
  lot_name: string
  slot_type: SlotType
  user: number
  vehicle: number
  vehicle_plate: string
  start_time: string
  end_time: string
  billed_hours: number
  hourly_rate: string
  base_amount: string
  refund_due_amount: string
  hold_expires_at: string | null
  cancelled_at: string | null
  actual_entry_at: string | null
  actual_exit_at: string | null
  overstay_hours: number
  overstay_amount: string
  created_at: string
  updated_at: string
}

export interface ConsumerBookingDetail extends ConsumerBooking {
  lot: number
  lot_address_line: string
  lot_city: string
  lot_state: string | null
  lot_postal_code: string | null
  slot_floor: number
  can_cancel: boolean
  can_extend: boolean
}

export interface OperatorBookingRow extends ConsumerBooking {
  lot: number
  consumer_email: string
  consumer_name: string
  can_check_in: boolean
  can_check_out: boolean
}

export interface ExtensionQuote {
  added_hours: number
  extension_amount: string
  new_billed_hours: number
  new_base_amount: string
  hourly_rate: string
  new_end_time: string
}

export type PaymentMethod = 'ONLINE' | 'CASH'
export type PaymentPurpose = 'BOOKING' | 'EXTENSION'
export type PaymentStatus = 'PENDING' | 'SUCCEEDED' | 'FAILED'
export type RefundStatus = 'PENDING' | 'SUCCEEDED' | 'FAILED'

export interface ConsumerPaymentRow {
  id: number
  booking: number
  booking_reference: string
  slot_number: string
  lot_code: string
  lot_name: string
  purpose: PaymentPurpose
  method: PaymentMethod
  status: PaymentStatus
  amount: string
  currency: string
  refunded_amount: string
  receipt_available: boolean
  paid_at: string | null
  created_at: string
}

export interface OperatorPaymentRow extends ConsumerPaymentRow {
  lot: number
  consumer: number
  consumer_email: string
  vehicle_plate: string
  extension_end_time: string | null
}

export interface PaymentInitiationResponse {
  id: number
  booking: number
  purpose: PaymentPurpose
  method: PaymentMethod
  status: PaymentStatus
  amount: string
  currency: string
  provider_order_id: string | null
  provider_payment_id: string | null
  extension_end_time: string | null
  failure_reason: string | null
  paid_at: string | null
  booking_applied: boolean
  created_at: string
  updated_at: string
  client_payload?: Record<string, unknown>
}

export interface RefundRow {
  id: number
  payment: number
  amount: string
  status: RefundStatus
  provider_refund_id: string | null
  reason: string
  created_at: string
  updated_at: string
}

export interface PaymentReceipt {
  receipt_number: string
  payment: number
  status: PaymentStatus
  amount: string
  currency: string
  method: PaymentMethod
  purpose: PaymentPurpose
  paid_at: string | null
  transaction_id: string | null
  booking: number
  booking_reference: string
  slot_number: string
  lot_code: string
  lot_name: string
  start_time: string
  end_time: string
  billed_hours: number
}

// Occupancy Board
export interface CurrentBookingSummary {
  id: number
  reference: string
  vehicle_plate: string
  status: BookingStatus
  start_time: string
  end_time: string
  actual_entry_at: string | null
  consumer_email: string
}

export interface OccupancyBoardSlot {
  id: number
  number: string
  floor: number
  slot_type: SlotType
  status: PhysicalSlotStatus
  current_booking: CurrentBookingSummary | null
}

export interface OccupancyBoard {
  lot: {
    id: number
    code: string
    name: string
  }
  generated_at: string
  summary: {
    total: number
    available: number
    occupied: number
    out_of_service: number
  }
  slots: OccupancyBoardSlot[]
}

// Reports
export interface ReportPeriod {
  from: string
  to: string
  timezone: string
}

export interface ReportScope {
  lot: number | null
  lots: number[]
}

export interface BookingsReport {
  period: ReportPeriod
  scope: ReportScope
  total: number
  by_status: Record<BookingStatus, number>
  active_now: number
  completed: number
  cancelled: number
}

export interface RevenueReport {
  period: ReportPeriod
  scope: ReportScope
  currency: 'INR'
  gross: string
  refunded: string
  net: string
  by_purpose: {
    BOOKING: string
    EXTENSION: string
  }
  payment_failures: number
  overstay_recorded: string
}

export interface OccupancyReport {
  scope: ReportScope
  period: ReportPeriod
  current: {
    total: number
    available: number
    occupied: number
    out_of_service: number
    rate: number
  }
  window: {
    bookings: number
    booked_hours: number
    bookable_hours: number
    booked_rate: number
  }
}

export interface PlatformReport {
  period: ReportPeriod
  users: {
    total: number
    active: number
    by_role: {
      CONSUMER: number
      MANAGER: number
      ADMIN: number
    }
  }
  lots: {
    total: number
    active: number
  }
  slots: {
    total: number
    by_status: {
      AVAILABLE: number
      OCCUPIED: number
      OUT_OF_SERVICE: number
    }
  }
  bookings: {
    total: number
    active_now: number
    completed: number
    cancelled: number
  }
  revenue: {
    gross: string
    refunded: string
    net: string
  }
  occupancy_rate: number
  payment_failures: number
  cancellations: number
}

// DRF Pagination Envelope (D66)
export interface PaginatedResponse<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

