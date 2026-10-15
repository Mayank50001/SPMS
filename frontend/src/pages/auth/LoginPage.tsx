// Login page
import React, { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { AuthTokens } from '../../api/types'
import { Button } from '../../components/common/Button'
import { Icon } from '../../components/common/Icon'

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setFieldErrors({})

    try {
      const tokens = await apiFetch<AuthTokens>('/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), password }),
      })

      login(tokens)

      // Role-aware default destination
      if (from) {
        navigate(from, { replace: true })
      } else if (tokens.user.role === 'ADMIN') {
        navigate('/admin', { replace: true })
      } else if (tokens.user.role === 'MANAGER') {
        navigate('/manager', { replace: true })
      } else {
        navigate('/consumer', { replace: true })
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) {
          setFieldErrors(err.fieldErrors)
        }
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Login failed. Please check your network connection.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-wrapper">
      <div className="auth-header">
        <span className="auth-logo">🅿️</span>
        <h1 className="auth-title">Welcome back</h1>
        <p className="auth-subtitle">Sign in to the Smart Parking Management System</p>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          <span className="alert-icon text-danger">
            <Icon name="alert" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Sign-in failed</p>
            <p>{error}</p>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit}>
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
            placeholder="user@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.email && <p className="form-error">{fieldErrors.email[0]}</p>}
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="password">
            Password <span className="required">*</span>
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="current-password"
            className={`form-control ${fieldErrors.password ? 'is-invalid' : ''}`}
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.password && <p className="form-error">{fieldErrors.password[0]}</p>}
        </div>

        <Button
          type="submit"
          variant="primary"
          size="lg"
          loading={loading}
          className="w-100 mt-2"
        >
          Sign In
        </Button>
      </form>

      <div className="auth-footer">
        Don&apos;t have an account?{' '}
        <Link to="/register" className="font-semibold text-primary">
          Create one
        </Link>
      </div>
    </div>
  )
}