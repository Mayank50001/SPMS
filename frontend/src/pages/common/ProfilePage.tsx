// Profile Management Page (Consumer, Manager, Admin)
import React, { useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { User } from '../../api/types'
import { Button } from '../../components/common/Button'
import { Card } from '../../components/common/Card'
import { RoleBadge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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

  const initials = (user.full_name || user.email || '?')
    .split(' ')
    .filter(Boolean)
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div>
      <PageHeader
        eyebrow="Account"
        title="Your profile"
        subtitle="Manage your personal information and review your account role"
        actions={<div className="profile-avatar">{initials}</div>}
      />

      <div className="grid grid-cols-2">
        <Card title="Personal information" subtitle="Update your contact details">
          {success && (
            <div className="alert alert-success" role="status">
              <span className="alert-icon text-success">
                <Icon name="check" size={18} />
              </span>
              <div className="alert-body">
                <p>Profile updated successfully.</p>
              </div>
            </div>
          )}

          {error && (
            <div className="alert alert-danger" role="alert">
              <span className="alert-icon text-danger">
                <Icon name="alert" size={18} />
              </span>
              <div className="alert-body">
                <p>{error}</p>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label" htmlFor="email">
                Email address
              </label>
              <input id="email" type="text" className="form-control" disabled value={user.email} />
              <p className="form-hint">Your email address cannot be changed.</p>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="fullName">
                Full name <span className="required">*</span>
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
              {fieldErrors.full_name && <p className="form-error">{fieldErrors.full_name[0]}</p>}
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="phone">
                Phone number
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
              {fieldErrors.phone && <p className="form-error">{fieldErrors.phone[0]}</p>}
            </div>

            <Button type="submit" variant="primary" loading={saving}>
              <Icon name="check" size={16} /> Save changes
            </Button>
          </form>
        </Card>

        <Card title="Account overview" subtitle="Your system role and metadata">
          <div className="info-list">
            <div className="info-row">
              <span className="info-label">Account role</span>
              <span className="info-value">
                <RoleBadge role={user.role} />
              </span>
            </div>
            <div className="info-row">
              <span className="info-label">Account ID</span>
              <span className="info-value font-mono">#{user.id}</span>
            </div>
            <div className="info-row">
              <span className="info-label">Member since</span>
              <span className="info-value">{formatDate(user.created_at)}</span>
            </div>
          </div>

          <div className="alert alert-info mt-3 mb-0">
            <span className="alert-icon text-primary">
              <Icon name="shield" size={18} />
            </span>
            <div className="alert-body">
              <p className="alert-title">Security note</p>
              <p>
                Session tokens rotate securely on each refresh. Permissions are enforced by
                server-side authorization.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}