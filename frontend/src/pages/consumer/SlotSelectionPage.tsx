// Slot Selection and Booking Initiation Page
import React, { useState } from 'react'
import { useParams, useSearchParams, Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ParkingLot, ParkingSlot, Vehicle, ConsumerBooking } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
      <div>
        <PageHeader
          eyebrow="Step 1 of 2"
          title="Choose a parking slot"
          subtitle="Pick your arrival and departure times to see live availability."
        />
        <EmptyState
          title="No booking window selected"
          message="Please specify your arrival and departure times before choosing a slot."
          action={
            <Link
              to={id ? `/consumer/lots/${id}` : '/consumer/search'}
              className="btn btn-primary btn-md"
            >
              Select a time window
            </Link>
          }
        />
      </div>
    )
  }

  return (
    <div>
      <Link to={`/consumer/lots/${id}`} className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to lot &amp; times
      </Link>

      <PageHeader
        eyebrow="Step 1 of 2 · Slot selection"
        title="Choose a parking slot"
        subtitle={
          <>
            {lot ? `${lot.name} (${lot.code})` : 'Parking facility'}
            <span className="text-subtle">
              {' '}· {formatDateTime(startIso)} → {formatDateTime(endIso)}
            </span>
          </>
        }
      />

      {bookingError && (
        <div className="alert alert-danger" role="alert">
          <span className="alert-icon text-danger">
            <Icon name="alert" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Reservation refused</p>
            <p>{bookingError}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3">
        {/* Slot Grid (takes 2 cols) */}
        <div className="grid-span-2">
          <Card
            title="Available slots"
            subtitle="Tap a slot to reserve it for your vehicle"
            action={
              <Button variant="outline" size="sm" onClick={() => refetchSlots()} disabled={loadingSlots}>
                <Icon name="search" size={15} /> Refresh
              </Button>
            }
          >
            {loadingSlots ? (
              <LoadingSpinner message="Checking real-time slot availability..." />
            ) : errorSlots ? (
              <ErrorState
                error={errorSlots}
                title="Could not retrieve available slots"
                onRetry={refetchSlots}
              />
            ) : availableSlots?.length === 0 ? (
              <EmptyState
                title="No slots available"
                message="Every slot at this facility is booked or out of service during your requested window."
                action={
                  <Link to={`/consumer/lots/${id}`} className="btn btn-secondary btn-md">
                    Change time window
                  </Link>
                }
              />
            ) : (
              <>
                <p className="muted-sm mb-0">
                  {availableSlots?.length}{' '}
                  {availableSlots?.length === 1 ? 'slot' : 'slots'} open for your window
                </p>

                <div className="slots-grid">
                  {availableSlots?.map((slot) => {
                    const isSelected = selectedSlot?.id === slot.id
                    return (
                      <div
                        key={slot.id}
                        className={`slot-tile ${isSelected ? 'slot-selected' : ''}`}
                        onClick={() => setSelectedSlot(slot)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            setSelectedSlot(slot)
                          }
                        }}
                        role="button"
                        tabIndex={0}
                        aria-pressed={isSelected}
                      >
                        {isSelected && (
                          <span className="slot-check">
                            <Icon name="check" size={12} />
                          </span>
                        )}
                        <span className="slot-type-badge">{slot.slot_type}</span>
                        <span className="slot-number">{slot.number}</span>
                        <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                          Floor {slot.floor}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </Card>
        </div>

        {/* Booking Summary (1 col) */}
        <div>
          <Card title="Booking summary" subtitle="Review and hold your slot">
            <form onSubmit={handleBookingSubmit}>
              <div className="form-group">
                <label className="form-label">Selected slot</label>
                {selectedSlot ? (
                  <div className="summary-box">
                    <span className="summary-box-label">Slot</span>
                    <div className="summary-box-value">{selectedSlot.number}</div>
                    <div className="muted-sm">
                      Floor {selectedSlot.floor} · {selectedSlot.slot_type}
                    </div>
                  </div>
                ) : (
                  <p className="text-muted" style={{ fontSize: '0.875rem' }}>
                    No slot selected yet — pick one from the grid.
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
                  <div className="alert alert-warning">
                    <span className="alert-icon">
                      <Icon name="alert" size={18} />
                    </span>
                    <div className="alert-body">
                      <p className="alert-title">No registered vehicles</p>
                      <p className="mb-2">Add a vehicle to complete your reservation.</p>
                      <Link to="/consumer/vehicles" className="btn btn-outline btn-sm">
                        <Icon name="plus" size={15} /> Add vehicle
                      </Link>
                    </div>
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
                <label className="form-label">Duration window</label>
                <div className="info-list">
                  <div className="info-row">
                    <span className="info-label">From</span>
                    <span className="info-value">{formatDateTime(startIso)}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">To</span>
                    <span className="info-value">{formatDateTime(endIso)}</span>
                  </div>
                </div>
              </div>

              <div className="alert alert-info">
                <span className="alert-icon text-primary">
                  <Icon name="info" size={18} />
                </span>
                <div className="alert-body">
                  <p className="alert-title">Slot hold policy</p>
                  <p>
                    Creating a reservation holds the slot temporarily. Complete payment before the
                    hold expires or the slot is released automatically.
                  </p>
                </div>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={!selectedSlot || !effectiveVehicleId || submitting}
                loading={submitting}
                className="w-100"
              >
                Proceed to payment <Icon name="arrowRight" size={16} />
              </Button>
            </form>
          </Card>
        </div>
      </div>
    </div>
  )
}