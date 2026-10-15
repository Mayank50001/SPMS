// Login page
import React, { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { AuthTokens } from '../../api/types'
import { Button } from '../../components/common/Button'

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
        <h1 className="auth-title">Welcome Back</h1>
        <p className="auth-subtitle">Sign in to your SPMS account</p>
      </div>

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
          {fieldErrors.email && (
            <p className="form-error">{fieldErrors.email[0]}</p>
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
            autoComplete="current-password"
            className={`form-control ${fieldErrors.password ? 'is-invalid' : ''}`}
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loading}
          />
          {fieldErrors.password && (
            <p className="form-error">{fieldErrors.password[0]}</p>
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
          Sign In
        </Button>
      </form>

      <div className="auth-footer">
        Don&apos;t have an account?{' '}
        <Link to="/register" className="font-semibold text-primary">
          Register here
        </Link>
      </div>
    </div>
  )
}

