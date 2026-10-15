// Parking Lot Search Page
import React, { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { City, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { Pagination } from '../../components/common/Pagination'

export const ParkingSearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const cityParam = searchParams.get('city') || ''
  const searchParam = searchParams.get('search') || ''

  const [selectedCity, setSelectedCity] = useState(cityParam)
  const [searchTerm, setSearchTerm] = useState(searchParam)

  // Cities are a bare array (D66)
  const { data: cities, loading: loadingCities } = useApi<City[]>('/cities/')

  // Parking lots are paginated
  const {
    results: lots,
    count,
    page,
    pageSize,
    totalPages,
    loading: loadingLots,
    error: errorLots,
    refetch: refetchLots,
    setPage,
  } = usePaginated<ParkingLot>('/parking-lots/', {
    params: {
      city: cityParam || undefined,
      search: searchParam || undefined,
    },
  })

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const nextParams = new URLSearchParams()
    if (selectedCity) nextParams.set('city', selectedCity)
    if (searchTerm.trim()) nextParams.set('search', searchTerm.trim())
    setSearchParams(nextParams)
  }

  const handleClear = () => {
    setSelectedCity('')
    setSearchTerm('')
    setSearchParams({})
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Find Parking</h1>
          <p className="page-subtitle">Search available parking facilities by city or location</p>
        </div>
      </div>

      {/* Filter / Search Bar */}
      <form onSubmit={handleFilterSubmit} className="filter-bar">
        <div style={{ flex: '1', minWidth: '180px' }}>
          <select
            className="form-control"
            value={selectedCity}
            onChange={(e) => setSelectedCity(e.target.value)}
            disabled={loadingCities}
          >
            <option value="">All Cities</option>
            {cities?.map((c) => (
              <option key={c.id} value={c.code}>
                {c.name} ({c.code})
              </option>
            ))}
          </select>
        </div>

        <div style={{ flex: '2', minWidth: '220px' }}>
          <input
            type="text"
            className="form-control"
            placeholder="Search by lot name or address..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <Button type="submit" variant="primary">
          Search
        </Button>
        {(cityParam || searchParam) && (
          <Button type="button" variant="outline" onClick={handleClear}>
            Clear Filters
          </Button>
        )}
      </form>

      {/* Results List */}
      {errorLots ? (
        <ErrorState error={errorLots} title="Failed to load parking lots" onRetry={refetchLots} />
      ) : loadingLots ? (
        <LoadingSpinner message="Searching parking lots..." />
      ) : lots.length === 0 ? (
        <EmptyState
          title="No parking lots found"
          message={
            cityParam || searchParam
              ? 'No parking lots matched your search criteria. Try broadening your filter.'
              : 'There are currently no active parking lots available.'
          }
          action={
            (cityParam || searchParam) ? (
              <Button variant="secondary" onClick={handleClear}>
                Reset Search
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-2 mb-4">
            {lots.map((lot) => (
              <Card key={lot.id} className="lot-card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                  <div>
                    <span className="badge badge-info" style={{ marginBottom: '0.25rem' }}>
                      {lot.city.name} · {lot.code}
                    </span>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 600 }}>{lot.name}</h3>
                  </div>
                </div>

                <p className="text-muted" style={{ fontSize: '0.875rem', marginBottom: '1rem' }}>
                  📍 {lot.address_line}
                  {lot.postal_code && `, ${lot.postal_code}`}
                  {lot.state && `, ${lot.state}`}
                </p>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-color)', paddingTop: '0.75rem' }}>
                  <span className="text-muted" style={{ fontSize: '0.8125rem' }}>
                    Active Facility
                  </span>
                  <Link to={`/consumer/lots/${lot.id}`} className="btn btn-primary btn-sm">
                    Select & Book Slot →
                  </Link>
                </div>
              </Card>
            ))}
          </div>

          <Pagination
            currentPage={page}
            totalPages={totalPages}
            totalItems={count}
            pageSize={pageSize}
            onPageChange={setPage}
            loading={loadingLots}
          />
        </>
      )}
    </div>
  )
}

