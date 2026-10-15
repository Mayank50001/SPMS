// Administrator Business Rules & Platform Policies Configuration (D35 / D45 / D70)
import React, { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { BusinessRules } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatDateTime } from '../../lib/format'

const BusinessRulesForm: React.FC<{ rules: BusinessRules; onSaved: () => Promise<void> }> = ({
  rules,
  onSaved,
}) => {
  const [maxHourlyRate, setMaxHourlyRate] = useState(rules.max_hourly_rate)
  const [maxBookingHours, setMaxBookingHours] = useState(String(rules.max_booking_hours))
  const [holdMinutes, setHoldMinutes] = useState(String(rules.hold_minutes))
  const [cutoffMinutes, setCutoffMinutes] = useState(String(rules.cancellation_cutoff_minutes))
  const [overstayMultiplier, setOverstayMultiplier] = useState(rules.overstay_multiplier)
  const [overstayGraceMinutes, setOverstayGraceMinutes] = useState(String(rules.overstay_grace_minutes))

  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setSaveError(null)
    setSuccess(false)
    setFieldErrors({})

    try {
      await apiFetch<BusinessRules>('/business-rules/', {
        method: 'PATCH',
        body: JSON.stringify({
          max_hourly_rate: maxHourlyRate,
          max_booking_hours: parseInt(maxBookingHours, 10),
          hold_minutes: parseInt(holdMinutes, 10),
          cancellation_cutoff_minutes: parseInt(cutoffMinutes, 10),
          overstay_multiplier: overstayMultiplier,
          overstay_grace_minutes: parseInt(overstayGraceMinutes, 10),
        }),
      })

      await onSaved()
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setSaveError(getFriendlyErrorMessage(err))
      } else {
        setSaveError('Failed to save business rules.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card title="Global Platform Parameters" subtitle={`Last updated: ${formatDateTime(rules.updated_at)}`}>
      {success && (
        <div className="mb-4 p-3" style={{ background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', borderRadius: '4px' }}>
          ✓ Business policies updated successfully and enforced across all facilities.
        </div>
      )}

      {saveError && (
        <div className="error-state mb-4" role="alert">
          <div className="error-icon">⚠️</div>
          <div className="error-content">
            <h4 className="error-title">Policy Update Refused</h4>
            <p className="error-message">{saveError}</p>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="form-row">
          <div className="form-col">
            <label className="form-label">
              Maximum Hourly Rate Cap (INR) <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.max_hourly_rate ? 'is-invalid' : ''}`}
              value={maxHourlyRate}
              onChange={(e) => setMaxHourlyRate(e.target.value)}
              disabled={saving}
            />
            {fieldErrors.max_hourly_rate && (
              <p className="form-error">{fieldErrors.max_hourly_rate[0]}</p>
            )}
            <p className="form-hint">No manager tariff may exceed this platform ceiling.</p>
          </div>

          <div className="form-col">
            <label className="form-label">
              Maximum Reservation Hours Cap <span className="required">*</span>
            </label>
            <input
              type="number"
              min={1}
              required
              className={`form-control ${fieldErrors.max_booking_hours ? 'is-invalid' : ''}`}
              value={maxBookingHours}
              onChange={(e) => setMaxBookingHours(e.target.value)}
              disabled={saving}
            />
            {fieldErrors.max_booking_hours && (
              <p className="form-error">{fieldErrors.max_booking_hours[0]}</p>
            )}
            <p className="form-hint">Platform ceiling for max_booking_hours across all slots.</p>
          </div>
        </div>

        <div className="form-row mt-3">
          <div className="form-col">
            <label className="form-label">
              Hold Duration Window (Minutes) <span className="required">*</span>
            </label>
            <input
              type="number"
              min={1}
              required
              className={`form-control ${fieldErrors.hold_minutes ? 'is-invalid' : ''}`}
              value={holdMinutes}
              onChange={(e) => setHoldMinutes(e.target.value)}
              disabled={saving}
            />
            {fieldErrors.hold_minutes && (
              <p className="form-error">{fieldErrors.hold_minutes[0]}</p>
            )}
            <p className="form-hint">Temporary hold lifetime for payment completion (D50).</p>
          </div>

          <div className="form-col">
            <label className="form-label">
              Cancellation Refund Cutoff (Minutes) <span className="required">*</span>
            </label>
            <input
              type="number"
              min={0}
              required
              className={`form-control ${fieldErrors.cancellation_cutoff_minutes ? 'is-invalid' : ''}`}
              value={cutoffMinutes}
              onChange={(e) => setCutoffMinutes(e.target.value)}
              disabled={saving}
            />
            {fieldErrors.cancellation_cutoff_minutes && (
              <p className="form-error">{fieldErrors.cancellation_cutoff_minutes[0]}</p>
            )}
            <p className="form-hint">Refund eligibility window before reservation start.</p>
          </div>
        </div>

        <div className="form-row mt-3">
          <div className="form-col">
            <label className="form-label">
              Overstay Multiplier (e.g. 1.50) <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.overstay_multiplier ? 'is-invalid' : ''}`}
              value={overstayMultiplier}
              onChange={(e) => setOverstayMultiplier(e.target.value)}
              disabled={saving}
            />
            {fieldErrors.overstay_multiplier && (
              <p className="form-error">{fieldErrors.overstay_multiplier[0]}</p>
            )}
            <p className="form-hint">Penalty multiplier applied to slot tariff rate on overstay.</p>
          </div>

          <div className="form-col">
            <label className="form-label">
              Overstay Grace Window (Minutes) <span className="required">*</span>
            </label>
            <input
              type="number"
              min={0}
              required
              className={`form-control ${fieldErrors.overstay_grace_minutes ? 'is-invalid' : ''}`}
              value={overstayGraceMinutes}
              onChange={(e) => setOverstayGraceMinutes(e.target.value)}
              disabled={saving}
            />
            {fieldErrors.overstay_grace_minutes && (
              <p className="form-error">{fieldErrors.overstay_grace_minutes[0]}</p>
            )}
            <p className="form-hint">Forgiven departure delay before overstay charge triggers.</p>
          </div>
        </div>

        <div className="mt-4 pt-3" style={{ borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="submit" variant="primary" size="lg" loading={saving}>
            Apply Business Policies
          </Button>
        </div>
      </form>
    </Card>
  )
}

export const BusinessRulesPage: React.FC = () => {
  const {
    data: rules,
    loading,
    error,
    refetch,
  } = useApi<BusinessRules>('/business-rules/')

  if (loading) return <LoadingSpinner message="Loading platform business policies..." />
  if (error || !rules) {
    return <ErrorState error={error} title="Could not load policies" onRetry={refetch} />
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Platform Business Rules</h1>
          <p className="page-subtitle">Configure system caps, cancellation cutoffs, and overstay multipliers</p>
        </div>
      </div>

      <div style={{ maxWidth: '800px' }}>
        <BusinessRulesForm key={rules.id} rules={rules} onSaved={refetch} />
      </div>
    </div>
  )
}
