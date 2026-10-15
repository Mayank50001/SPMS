// Unified API Client with single-flight JWT token refresh (D80)
import { ApiError } from './errors'

const ACCESS_KEY = 'spms_access_token'
const REFRESH_KEY = 'spms_refresh_token'
const USER_KEY = 'spms_user'

export function getStoredAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setStoredAuth(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearStoredAuth(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
}

let refreshingPromise: Promise<boolean> | null = null

// Auth-expiry callback — set by AuthProvider on mount (Bug 2 fix)
let onAuthExpired: (() => void) | null = null
export function setAuthExpiredCallback(fn: () => void): void {
  onAuthExpired = fn
}

async function doTokenRefresh(): Promise<boolean> {
  const currentRefresh = getStoredRefreshToken()
  if (!currentRefresh) {
    onAuthExpired?.()
    return false
  }

  try {
    const res = await fetch('/api/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: currentRefresh }),
    })

    if (!res.ok) {
      clearStoredAuth()
      onAuthExpired?.()
      return false
    }

    const data = await res.json()
    // Rotation is ON (D17): must store the NEW refresh token alongside the new access token
    if (data.access && data.refresh) {
      setStoredAuth(data.access, data.refresh)
      return true
    }
    clearStoredAuth()
    onAuthExpired?.()
    return false
  } catch {
    clearStoredAuth()
    onAuthExpired?.()
    return false
  }
}

function refreshOnce(): Promise<boolean> {
  if (!refreshingPromise) {
    refreshingPromise = doTokenRefresh().finally(() => {
      refreshingPromise = null
    })
  }
  return refreshingPromise
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {}
  try {
    body = await res.json()
  } catch {
    return new ApiError(res.status, undefined, undefined, `HTTP error ${res.status}: ${res.statusText}`)
  }

  // Coded business refusal shape: { "error": "CODE", "message": "..." }
  if (typeof body.error === 'string') {
    const message = typeof body.message === 'string' ? body.message : undefined
    return new ApiError(res.status, body.error, undefined, message)
  }

  // Field validation errors: { [field]: string[] } or detail
  if (typeof body.detail === 'string') {
    return new ApiError(res.status, undefined, undefined, body.detail)
  }

  const fieldErrors: Record<string, string[]> = {}
  let hasFieldErrors = false
  for (const [key, val] of Object.entries(body)) {
    if (Array.isArray(val) && val.every((v) => typeof v === 'string')) {
      fieldErrors[key] = val
      hasFieldErrors = true
    } else if (typeof val === 'string') {
      fieldErrors[key] = [val]
      hasFieldErrors = true
    }
  }

  if (hasFieldErrors) {
    const primaryMsg = Object.values(fieldErrors)[0]?.[0] || 'Validation error'
    return new ApiError(res.status, undefined, fieldErrors, primaryMsg)
  }

  return new ApiError(res.status, undefined, undefined, `Request failed with status ${res.status}`)
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getStoredAccessToken()
  const headers = new Headers(init.headers || {})
  if (!headers.has('Content-Type') && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  // Clean trailing slash normalization
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  const normalizedPath = cleanPath.includes('?') 
    ? cleanPath.replace(/([^/])\?/, '$1/?')
    : (cleanPath.endsWith('/') ? cleanPath : `${cleanPath}/`)

  const res = await fetch(`/api${normalizedPath}`, {
    ...init,
    headers,
  })

  // Handle 401 with single-flight silent refresh
  if (res.status === 401 && !path.startsWith('/auth/login') && !path.startsWith('/auth/register')) {
    const refreshed = await refreshOnce()
    if (refreshed) {
      const retryToken = getStoredAccessToken()
      const retryHeaders = new Headers(init.headers || {})
      if (!retryHeaders.has('Content-Type') && !(init.body instanceof FormData)) {
        retryHeaders.set('Content-Type', 'application/json')
      }
      if (retryToken) {
        retryHeaders.set('Authorization', `Bearer ${retryToken}`)
      }
      const retryRes = await fetch(`/api${normalizedPath}`, {
        ...init,
        headers: retryHeaders,
      })
      if (!retryRes.ok) {
        throw await toApiError(retryRes)
      }
      if (retryRes.status === 204) return undefined as T
      return retryRes.json()
    }
    // Failed refresh: raise 401 ApiError
    throw new ApiError(401, 'UNAUTHORIZED', undefined, 'Your session has expired. Please log in again.')
  }

  if (!res.ok) {
    throw await toApiError(res)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return res.json()
}

