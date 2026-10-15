// Route guards for authentication and role authorization (UX-level guard; backend is authoritative)
import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './useAuth'
import type { UserRole } from '../api/types'

export const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { user, loading, isAuthenticated } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="center-screen">
        <div className="spinner" />
        <p>Loading session...</p>
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}

export const RequireRole: React.FC<{
  roles: UserRole[]
  children: React.ReactNode
}> = ({ roles, children }) => {
  const { user, loading, isAuthenticated } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="center-screen">
        <div className="spinner" />
        <p>Checking permissions...</p>
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (!roles.includes(user.role)) {
    // Redirect to the user's home dashboard rather than a dead-end
    if (user.role === 'ADMIN') return <Navigate to="/admin" replace />
    if (user.role === 'MANAGER') return <Navigate to="/manager" replace />
    return <Navigate to="/consumer" replace />
  }

  return <>{children}</>
}

export const RoleRedirect: React.FC = () => {
  const { user, loading, isAuthenticated } = useAuth()

  if (loading) {
    return (
      <div className="center-screen">
        <div className="spinner" />
      </div>
    )
  }

  if (!isAuthenticated || !user) {
    return <Navigate to="/login" replace />
  }

  if (user.role === 'ADMIN') return <Navigate to="/admin" replace />
  if (user.role === 'MANAGER') return <Navigate to="/manager" replace />
  return <Navigate to="/consumer" replace />
}

