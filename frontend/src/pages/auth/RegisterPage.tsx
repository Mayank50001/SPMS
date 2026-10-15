// Register page (Consumer self-registration)
import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { RegisterResponse } from '../../api/types'
import { Button } from '../../components/common/Button'

export const RegisterPage: React.FC = () => {
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [passwordConfirm, setPasswordConfirm] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})
  const [success, setSuccess] = useState(false)

  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setFieldErrors({})

    if (password !== passwordConfirm) {
      setFieldErrors({ password_confirm: ['Passwords do not match'] })
      setLoading(false)
      return
    }

    try {
      await apiFetch<RegisterResponse>('/auth/register/', {
        method: 'POST',
        body: JSON.stringify({
          email: email.trim(),
          full_name: fullName.trim(),
          phone: phone.trim() || undefined,
          password,
          password_confirm: passwordConfirm,
        }),
      })

      setSuccess(true)
      setTimeout(() => {
        navigate('/login')
      }, 1500)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) {
          setFieldErrors(err.fieldErrors)
        }
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Registration failed. Please try again.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-wrapper">
      <div className="auth-header">
        <h1 className="auth-title">Create Account</h1>
        <p className="auth-subtitle">Register as an SPMS Consumer</p>
      </div>

      {success && (
        <div className="mb-4 p-3 bg-success text-center" style={{ background: '#f0fdf4', color: '#16a34a', border: '1px solid #bbf7d0', borderRadius: '4px' }}>
          ✓ Registration successful! Redirecting to login...
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
          <label className="form-label" htmlFor="fullName">
            Full Name <span className="required">*</span>
          </label>
          <input
            id="fullName"
            type="text"
            required
            className={`form-control ${fieldErrors.full_name ? 'is-invalid' : ''}`}
            placeholder="Jane Doe"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.full_name && (
            <p className="form-error">{fieldErrors.full_name[0]}</p>
          )}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="email">
            Email address <span className="required">*</span>
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            className={`form-control ${fieldErrors.email ? 'is-invalid' : ''}`}
            placeholder="jane@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.email && (
            <p className="form-error">{fieldErrors.email[0]}</p>
          )}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="phone">
            Phone Number (optional)
          </label>
          <input
            id="phone"
            type="tel"
            className={`form-control ${fieldErrors.phone ? 'is-invalid' : ''}`}
            placeholder="+91 9876543210"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.phone && (
            <p className="form-error">{fieldErrors.phone[0]}</p>
          )}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="password">
            Password <span className="required">*</span>
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="new-password"
            className={`form-control ${fieldErrors.password ? 'is-invalid' : ''}`}
            placeholder="Minimum 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.password && (
            <p className="form-error">{fieldErrors.password[0]}</p>
          )}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="passwordConfirm">
            Confirm Password <span className="required">*</span>
          </label>
          <input
            id="passwordConfirm"
            type="password"
            required
            autoComplete="new-password"
            className={`form-control ${fieldErrors.password_confirm ? 'is-invalid' : ''}`}
            placeholder="Re-enter password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.password_confirm && (
            <p className="form-error">{fieldErrors.password_confirm[0]}</p>
          )}
        </div>

        <Button
          type="submit"
          variant="primary"
          size="md"
          loading={loading}
          className="w-100 mt-2"
          style={{ width: '100%' }}
        >
          Create Account
        </Button>
      </form>

      <div className="auth-footer">
        Already have an account?{' '}
        <Link to="/login" className="font-semibold text-primary">
          Sign In
        </Link>
      </div>
    </div>
  )
}

