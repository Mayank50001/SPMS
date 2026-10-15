// Profile Management Page (Consumer, Manager, Admin)
import React, { useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { User } from '../../api/types'
import { Button } from '../../components/common/Button'
import { Card } from '../../components/common/Card'
import { RoleBadge } from '../../components/common/Badge'
import { formatDate } from '../../lib/format'

export const ProfilePage: React.FC = () => {
  const { user, refreshProfile } = useAuth()
  const [fullName, setFullName] = useState(user?.full_name || '')
  const [phone, setPhone] = useState(user?.phone || '')

  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setSuccess(false)
    setFieldErrors({})

    try {
      await apiFetch<User>('/auth/me/', {
        method: 'PATCH',
        body: JSON.stringify({
          full_name: fullName.trim(),
          phone: phone.trim() || null,
        }),
      })

      await refreshProfile()
      setSuccess(true)
      setTimeout(() => setSuccess(false), 3000)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to update profile.')
      }
    } finally {
      setSaving(false)
    }
  }

  if (!user) return null

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Account Profile</h1>
          <p className="page-subtitle">Manage your personal information and view role permissions</p>
        </div>
      </div>

      <div className="grid grid-cols-2">
        <Card title="Personal Information" subtitle="Update your contact details">
          {success && (
            <div className="mb-4 p-3" style={{ background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', borderRadius: '4px' }}>
              ✓ Profile updated successfully.
            </div>
          )}

          {error && (
            <div className="error-state mb-4" role="alert">
              <div className="error-icon">⚠️</div>
              <div className="error-content">
                <p className="error-message">{error}</p>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="email">
                Email Address
              </label>
              <input
                id="email"
                type="text"
                className="form-control"
                disabled
                value={user.email}
              />
              <p className="form-hint">Email address cannot be changed.</p>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="fullName">
                Full Name <span className="required">*</span>
              </label>
              <input
                id="fullName"
                type="text"
                required
                className={`form-control ${fieldErrors.full_name ? 'is-invalid' : ''}`}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                disabled={saving}
              />
              {fieldErrors.full_name && (
                <p className="form-error">{fieldErrors.full_name[0]}</p>
              )}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="phone">
                Phone Number
              </label>
              <input
                id="phone"
                type="tel"
                className={`form-control ${fieldErrors.phone ? 'is-invalid' : ''}`}
                placeholder="+91 9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                disabled={saving}
              />
              {fieldErrors.phone && (
                <p className="form-error">{fieldErrors.phone[0]}</p>
              )}
            </div>

            <Button type="submit" variant="primary" loading={saving}>
              Save Changes
            </Button>
          </form>
        </Card>

        <Card title="Account Overview" subtitle="System role and metadata">
          <div className="info-list" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div>
              <span className="text-muted" style={{ fontSize: '0.8125rem', display: 'block' }}>Account Role</span>
              <div style={{ marginTop: '0.25rem' }}>
                <RoleBadge role={user.role} />
              </div>
            </div>

            <div>
              <span className="text-muted" style={{ fontSize: '0.8125rem', display: 'block' }}>Account ID</span>
              <span className="font-mono" style={{ fontSize: '0.9375rem' }}>#{user.id}</span>
            </div>

            <div>
              <span className="text-muted" style={{ fontSize: '0.8125rem', display: 'block' }}>Member Since</span>
              <span>{formatDate(user.created_at)}</span>
            </div>

            <div style={{ padding: '0.75rem', background: '#f8fafc', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
              <strong style={{ fontSize: '0.8125rem', display: 'block', marginBottom: '0.25rem' }}>Security Note</strong>
              <p style={{ fontSize: '0.8125rem', color: '#64748b' }}>
                Session tokens rotate securely with each refresh. Permissions are enforced by server-side authorization.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

