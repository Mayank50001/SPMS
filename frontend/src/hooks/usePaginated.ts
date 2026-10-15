// Hook for DRF paginated collections (D66)
import { useState, useEffect, useCallback, useMemo } from 'react'
import { apiFetch } from '../api/client'
import { ApiError } from '../api/errors'
import type { PaginatedResponse } from '../api/types'

interface UsePaginatedOptions {
  pageSize?: number
  params?: Record<string, string | number | boolean | undefined | null>
  skip?: boolean
}

interface UsePaginatedState<T> {
  results: T[]
  count: number
  page: number
  pageSize: number
  totalPages: number
  loading: boolean
  error: ApiError | null
  setPage: (page: number) => void
  refetch: () => Promise<void>
}

export function usePaginated<T>(
  basePath: string,
  options: UsePaginatedOptions = {}
): UsePaginatedState<T> {
  const { pageSize = 20, params = {}, skip = false } = options
  const [page, setPage] = useState<number>(1)

  // Reset to page 1 whenever filter params change (Bug 3 fix). React's
  // documented "adjust state during render" pattern: the stale page is never
  // rendered/fetched, unlike an effect-based reset which fires a wasted request.
  const paramsKey = JSON.stringify(params)
  const [lastParamsKey, setLastParamsKey] = useState(paramsKey)
  if (paramsKey !== lastParamsKey) {
    setLastParamsKey(paramsKey)
    setPage(1)
  }

  const [data, setData] = useState<PaginatedResponse<T> | null>(null)
  const [loading, setLoading] = useState<boolean>(!skip)
  const [error, setError] = useState<ApiError | null>(null)

  const queryString = useMemo(() => {
    const sp = new URLSearchParams()
    sp.set('page', String(page))
    sp.set('page_size', String(pageSize))

    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null && val !== '') {
        sp.set(key, String(val))
      }
    }
    return sp.toString()
  }, [page, pageSize, params])

  const fetchData = useCallback(async () => {
    if (skip) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const sep = basePath.includes('?') ? '&' : '?'
      const fullPath = `${basePath}${sep}${queryString}`
      const response = await apiFetch<PaginatedResponse<T>>(fullPath)
      setData(response)
    } catch (err) {
      setData(null)
      if (err instanceof ApiError) {
        setError(err)
      } else {
        setError(new ApiError(0, undefined, undefined, (err as Error).message))
      }
    } finally {
      setLoading(false)
    }
  }, [basePath, queryString, skip])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- standard fetch-on-mount loader
    fetchData()
  }, [fetchData])

  const count = data?.count ?? 0
  const totalPages = Math.max(1, Math.ceil(count / pageSize))

  return {
    results: data?.results ?? [],
    count,
    page,
    pageSize,
    totalPages,
    loading,
    error,
    setPage,
    refetch: fetchData,
  }
}

