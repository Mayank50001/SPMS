// Slot Selection and Booking Initiation Page
import React, { useState } from 'react'
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ParkingLot, ParkingSlot, Vehicle, ConsumerBooking } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { EmptyState } from '../../components/common/EmptyState'
import { formatDateTime } from '../../lib/format'

export const SlotSelectionPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const startIso = searchParams.get('start') || ''
  const endIso = searchParams.get('end') || ''

  const [selectedSlot, setSelectedSlot] = useState<ParkingSlot | null>(null)
  const [selectedVehicleId, setSelectedVehicleId] = useState<number | ''>('')
  const [submitting, setSubmitting] = useState(false)
  const [bookingError, setBookingError] = useState<string | null>(null)

  // Fetch lot details
  const { data: lot } = useApi<ParkingLot>(id ? `/parking-lots/${id}/` : null)

  // Fetch bookable availability (bare array per D66)
  const availabilityPath = id && startIso && endIso
    ? `/parking-lots/${id}/availability/?start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`
    : null

  const {
    data: availableSlots,
    loading: loadingSlots,
    error: errorSlots,
    refetch: refetchSlots,
  } = useApi<ParkingSlot[]>(availabilityPath)

  // Fetch user's registered vehicles
  const {
    data: vehiclesData,
    loading: loadingVehicles,
  } = useApi<{ count: number; results: Vehicle[] }>('/vehicles/')

  const vehicles = React.useMemo(() => vehiclesData?.results || [], [vehiclesData?.results])
  const effectiveVehicleId = selectedVehicleId !== '' ? selectedVehicleId : (vehicles[0]?.id ?? '')

  const handleBookingSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedSlot) {
      setBookingError('Please choose a parking slot from the grid below.')
      return
    }
    if (!effectiveVehicleId) {
      setBookingError('Please select a registered vehicle for this reservation.')
      return
    }

    setSubmitting(true)
    setBookingError(null)

    try {
      const newBooking = await apiFetch<ConsumerBooking>('/bookings/', {
        method: 'POST',
        body: JSON.stringify({
          slot: selectedSlot.id,
          vehicle: effectiveVehicleId,
          start_time: startIso,
          end_time: endIso,
        }),
      })

      // Successfully created hold, route to payment
      navigate(`/consumer/payment/${newBooking.id}`)
    } catch (err) {
      if (err instanceof ApiError) {
        setBookingError(getFriendlyErrorMessage(err))
        if (err.status === 409) {
          // Conflict: slot was taken. Re-fetch availability and unselect slot
          setSelectedSlot(null)
          refetchSlots()
        }
      } else {
        setBookingError('An error occurred while creating your reservation.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (!startIso || !endIso) {
    return (
      <div className="empty-state">
        <h3 className="empty-state-title">No booking window selected</h3>
        <p className="empty-state-message">Please specify your arrival and departure times first.</p>
        <Link to={`/consumer/lots/${id}`} className="btn btn-primary mt-4">
          Select Window
        </Link>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-2">
        <Link to={`/consumer/lots/${id}`} className="text-muted" style={{ fontSize: '0.875rem' }}>
          ← Back to Lot Details & Times
        </Link>
      </div>

      <div className="page-header">
        <div>
          <h1 className="page-title">Select Parking Slot</h1>
          <p className="page-subtitle">
            {lot ? `${lot.name} (${lot.code})` : 'Parking Facility'} · Window: {formatDateTime(startIso)} → {formatDateTime(endIso)}
          </p>
        </div>
      </div>

      {bookingError && (
        <div className="error-state mb-4" role="alert">
          <div className="error-icon">⚠️</div>
          <div className="error-content">
            <h4 className="error-title">Reservation Refused</h4>
            <p className="error-message">{bookingError}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3">
        {/* Slot Grid (takes 2 cols) */}
        <div style={{ gridColumn: 'span 2' }}>
          <Card
            title="Available Slots"
            subtitle="Click on a slot to select it for your vehicle"
            action={
              <Button variant="outline" size="sm" onClick={() => refetchSlots()} disabled={loadingSlots}>
                ↻ Refresh Availability
              </Button>
            }
          >
            {loadingSlots ? (
              <LoadingSpinner message="Checking real-time slot availability..." />
            ) : errorSlots ? (
              <ErrorState error={errorSlots} title="Could not retrieve available slots" onRetry={refetchSlots} />
            ) : availableSlots?.length === 0 ? (
              <EmptyState
                title="No slots available"
                message="All slots for this facility are currently booked or out of service during your requested window."
                action={
                  <Link to={`/consumer/lots/${id}`} className="btn btn-secondary btn-sm">
                    Change Time Window
                  </Link>
                }
              />
            ) : (
              <div className="slots-grid">
                {availableSlots?.map((slot) => {
                  const isSelected = selectedSlot?.id === slot.id
                  return (
                    <div
                      key={slot.id}
                      className={`slot-tile ${isSelected ? 'slot-selected' : ''}`}
                      onClick={() => setSelectedSlot(slot)}
                      role="button"
                      tabIndex={0}
                    >
                      <span className="slot-type-badge">{slot.slot_type}</span>
                      <span className="slot-number">{slot.number}</span>
                      <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                        Floor {slot.floor}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        </div>

        {/* Booking Confirmation Sidebar (1 col) */}
        <div>
          <Card title="Booking Summary" subtitle="Review and confirm hold">
            <form onSubmit={handleBookingSubmit}>
              <div className="form-group">
                <label className="form-label">Selected Slot</label>
                {selectedSlot ? (
                  <div style={{ padding: '0.75rem', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '4px' }}>
                    <div style={{ fontWeight: 700, fontSize: '1.125rem' }}>Slot {selectedSlot.number}</div>
                    <div style={{ fontSize: '0.8125rem', color: '#1e40af' }}>
                      Floor {selectedSlot.floor} · Type: {selectedSlot.slot_type}
                    </div>
                  </div>
                ) : (
                  <p className="text-muted" style={{ fontSize: '0.875rem' }}>
                    Click a slot in the grid to select.
                  </p>
                )}
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="vehicleSelect">
                  Vehicle <span className="required">*</span>
                </label>
                {loadingVehicles ? (
                  <LoadingSpinner size="sm" />
                ) : vehicles.length === 0 ? (
                  <div style={{ padding: '0.75rem', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '4px' }}>
                    <p style={{ fontSize: '0.8125rem', color: '#92400e', marginBottom: '0.5rem' }}>
                      You have no registered vehicles.
                    </p>
                    <Link to="/consumer/vehicles" className="btn btn-outline btn-sm">
                      + Add Vehicle
                    </Link>
                  </div>
                ) : (
                  <select
                    id="vehicleSelect"
                    className="form-control"
                    value={effectiveVehicleId}
                    onChange={(e) => setSelectedVehicleId(Number(e.target.value))}
                    required
                  >
                    {vehicles.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.registration_number} {v.make ? `(${v.make} ${v.model || ''})` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">Duration Window</label>
                <div style={{ fontSize: '0.8125rem', color: '#475569' }}>
                  <div><strong>From:</strong> {formatDateTime(startIso)}</div>
                  <div><strong>To:</strong> {formatDateTime(endIso)}</div>
                </div>
              </div>

              <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '4px', border: '1px solid #e2e8f0', marginBottom: '1rem' }}>
                <strong style={{ fontSize: '0.8125rem', display: 'block', marginBottom: '0.25rem' }}>Hold Policy (D50)</strong>
                <p style={{ fontSize: '0.75rem', color: '#64748b' }}>
                  Creating a reservation holds the slot temporarily for payment. If payment is not completed before the hold window expires, the slot is automatically released.
                </p>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={!selectedSlot || !selectedVehicleId || submitting}
                loading={submitting}
                className="w-100"
                style={{ width: '100%' }}
              >
                Proceed to Payment →
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}

