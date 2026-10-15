// Authentication Provider
import React, { useEffect, useState, useCallback } from 'react'
import { apiFetch, clearStoredAuth, getStoredAccessToken, setStoredAuth, setAuthExpiredCallback } from '../api/client'
import type { AuthTokens, User } from '../api/types'
import { AuthContext } from './context'

const USER_STORAGE_KEY = 'spms_user'

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const raw = localStorage.getItem(USER_STORAGE_KEY)
    if (!raw) return null
    try {
      return JSON.parse(raw) as User
    } catch {
      return null
    }
  })
  const [loading, setLoading] = useState<boolean>(true)

  const refreshProfile = useCallback(async () => {
    const token = getStoredAccessToken()
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }

    try {
      const me = await apiFetch<User>('/auth/me/')
      setUser(me)
      localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(me))
    } catch {
      setUser(null)
      clearStoredAuth()
    } finally {
      setLoading(false)
    }
  }, [])

  // Register auth-expiry callback so the API client can clear React state on session loss (Bug 2 fix)
  useEffect(() => {
    setAuthExpiredCallback(() => {
      clearStoredAuth()
      setUser(null)
    })
  }, [])

  useEffect(() => {
    refreshProfile()
  }, [refreshProfile])

  const login = useCallback((tokens: AuthTokens) => {
    setStoredAuth(tokens.access, tokens.refresh)
    setUser(tokens.user)
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(tokens.user))
  }, [])

  const logout = useCallback(async () => {
    const refresh = localStorage.getItem('spms_refresh_token')
    if (refresh) {
      try {
        await apiFetch('/auth/logout/', {
          method: 'POST',
          body: JSON.stringify({ refresh }),
        })
      } catch {
        // Ignore logout network errors
      }
    }
    clearStoredAuth()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}
