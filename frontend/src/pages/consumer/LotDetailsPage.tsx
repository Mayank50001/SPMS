// Parking Lot Details & Tariff inspection
import React, { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { ParkingLot, Tariff } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'
import { PageHeader } from '../../components/common/PageHeader'
import { Icon } from '../../components/common/Icon'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatMoney, toDatetimeLocalValue } from '../../lib/format'

export const LotDetailsPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // Default time window: upcoming next hour, for 2 hours duration
  const [startTime, setStartTime] = useState(() => {
    const d = new Date()
    d.setHours(d.getHours() + 1, 0, 0, 0)
    return toDatetimeLocalValue(d)
  })

  const [endTime, setEndTime] = useState(() => {
    const d = new Date()
    d.setHours(d.getHours() + 3, 0, 0, 0)
    return toDatetimeLocalValue(d)
  })

  const [windowError, setWindowError] = useState<string | null>(null)

  // Fetch lot details
  const {
    data: lot,
    loading: loadingLot,
    error: errorLot,
    refetch: refetchLot,
  } = useApi<ParkingLot>(id ? `/parking-lots/${id}/` : null)

  // Fetch tariffs for this lot
  const {
    results: tariffs,
    loading: loadingTariffs,
  } = usePaginated<Tariff>(id ? `/parking-lots/${id}/tariffs/` : '', {
    pageSize: 50,
    skip: !id,
  })

  const handleProceedToSlots = (e: React.FormEvent) => {
    e.preventDefault()
    setWindowError(null)

    const start = new Date(startTime)
    const end = new Date(endTime)

    if (isNaN(start.getTime()) || isNaN(end.getTime())) {
      setWindowError('Please provide both valid start and end dates/times.')
      return
    }

    if (start >= end) {
      setWindowError('End time must be after start time.')
      return
    }

    if (start < new Date(Date.now() - 5 * 60 * 1000)) {
      setWindowError('Start time cannot be in the past.')
      return
    }

    // Convert to ISO UTC string for API query
    const startIso = start.toISOString()
    const endIso = end.toISOString()

    navigate(
      `/consumer/lots/${id}/slots?start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`
    )
  }

  if (loadingLot) return <LoadingSpinner message="Loading parking lot details..." />
  if (errorLot || !lot) {
    return <ErrorState error={errorLot} title="Parking lot not found" onRetry={refetchLot} />
  }

  return (
    <div>
      <Link to="/consumer/search" className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to search
      </Link>

      <PageHeader
        eyebrow={<Badge variant="info">{lot.code}</Badge>}
        title={lot.name}
        subtitle={
          <span className="flex items-center gap-2">
            <Icon name="mapPin" size={15} className="text-subtle" />
            <span>
              {lot.address_line}, {lot.city.name} ({lot.city.code})
              {lot.postal_code ? ` ${lot.postal_code}` : ''}
            </span>
          </span>
        }
      />

      <div className="grid grid-cols-2">
        {/* Reservation Window Selection */}
        <Card title="Select booking window" subtitle="Choose when you will park">
          {windowError && (
            <div className="alert alert-danger" role="alert">
              <span className="alert-icon text-danger">
                <Icon name="alert" size={18} />
              </span>
              <div className="alert-body">
                <p>{windowError}</p>
              </div>
            </div>
          )}

          <form onSubmit={handleProceedToSlots}>
            <div className="form-group">
              <label className="form-label" htmlFor="startTime">
                Arrival time (start) <span className="required">*</span>
              </label>
              <input
                id="startTime"
                type="datetime-local"
                required
                className="form-control"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
              />
              <p className="form-hint">Shown in your local browser time (stored in UTC).</p>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="endTime">
                Departure time (end) <span className="required">*</span>
              </label>
              <input
                id="endTime"
                type="datetime-local"
                required
                className="form-control"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
              />
            </div>

            <Button type="submit" variant="primary" size="lg" className="w-100 mt-2">
              Check available slots <Icon name="arrowRight" size={16} />
            </Button>
          </form>
        </Card>

        {/* Pricing / Tariff Table */}
        <Card title="Standard tariffs" subtitle="Hourly rates by vehicle type">
          {loadingTariffs ? (
            <LoadingSpinner size="sm" message="Loading tariff rates..." />
          ) : tariffs.length === 0 ? (
            <p className="text-muted">No pricing tariffs published yet for this facility.</p>
          ) : (
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Vehicle Type</th>
                    <th>Hourly Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {tariffs.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <strong>{t.slot_type_label || t.slot_type}</strong>{' '}
                        <Badge variant="neutral">{t.slot_type}</Badge>
                      </td>
                      <td className="font-semibold">{formatMoney(t.hourly_rate)} / hr</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}