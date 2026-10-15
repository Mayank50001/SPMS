// Hook for generic API queries
import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'
import { ApiError } from '../api/errors'

interface UseApiState<T> {
  data: T | null
  loading: boolean
  error: ApiError | null
  refetch: () => Promise<void>
}

export function useApi<T>(
  path: string | null,
  options?: {
    skip?: boolean
  }
): UseApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState<boolean>(!options?.skip && !!path)
  const [error, setError] = useState<ApiError | null>(null)

  const fetchData = useCallback(async () => {
    if (!path || options?.skip) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const result = await apiFetch<T>(path)
      setData(result)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err)
      } else {
        setError(new ApiError(0, undefined, undefined, (err as Error).message))
      }
    } finally {
      setLoading(false)
    }
  }, [path, options?.skip])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  return { data, loading, error, refetch: fetchData }
}

