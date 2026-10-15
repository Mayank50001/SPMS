// Administrator Business Rules & Platform Policies Configuration (D35 / D45 / D70)
import React, { useState } from 'react'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { BusinessRules } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
    <Card title="Global platform parameters" subtitle={`Last updated: ${formatDateTime(rules.updated_at)}`}>
      {success && (
        <div className="alert alert-success" role="status">
          <span className="alert-icon text-success">
            <Icon name="check" size={18} />
          </span>
          <div className="alert-body">
            <p>Business policies updated successfully and enforced across all facilities.</p>
          </div>
        </div>
      )}

      {saveError && (
        <div className="alert alert-danger" role="alert">
          <span className="alert-icon text-danger">
            <Icon name="alert" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Policy update refused</p>
            <p>{saveError}</p>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <h4 className="form-section-title form-section-title-first">Rate &amp; duration caps</h4>
        <div className="form-row">
          <div className="form-col">
            <label className="form-label">
              Maximum hourly rate cap (INR) <span className="required">*</span>
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
              Maximum reservation hours cap <span className="required">*</span>
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

        <h4 className="form-section-title">Timing policies</h4>
        <div className="form-row">
          <div className="form-col">
            <label className="form-label">
              Hold duration window (minutes) <span className="required">*</span>
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
            {fieldErrors.hold_minutes && <p className="form-error">{fieldErrors.hold_minutes[0]}</p>}
            <p className="form-hint">Temporary hold lifetime for payment completion (D50).</p>
          </div>

          <div className="form-col">
            <label className="form-label">
              Cancellation refund cutoff (minutes) <span className="required">*</span>
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

        <h4 className="form-section-title">Overstay policy</h4>
        <div className="form-row">
          <div className="form-col">
            <label className="form-label">
              Overstay multiplier (e.g. 1.50) <span className="required">*</span>
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
            <p className="form-hint">Penalty multiplier applied to the slot tariff rate on overstay.</p>
          </div>

          <div className="form-col">
            <label className="form-label">
              Overstay grace window (minutes) <span className="required">*</span>
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

        <div className="divider-top mt-4" style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button type="submit" variant="primary" size="lg" loading={saving}>
            <Icon name="check" size={16} /> Apply business policies
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
      <PageHeader
        eyebrow="Governance"
        title="Platform business rules"
        subtitle="Configure system caps, cancellation cutoffs and overstay multipliers"
      />

      <div style={{ maxWidth: '820px' }}>
        <BusinessRulesForm key={rules.id} rules={rules} onSaved={refetch} />
      </div>
    </div>
  )
}