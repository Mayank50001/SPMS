// Parking Lot Search Page
import React, { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import { usePaginated } from '../../hooks/usePaginated'
import type { City, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'
import { PageHeader } from '../../components/common/PageHeader'
import { Icon } from '../../components/common/Icon'
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
      <PageHeader
        eyebrow="Find Parking"
        title="Parking facilities"
        subtitle="Search available parking facilities by city or location"
      />

      {/* Filter / Search Bar */}
      <form onSubmit={handleFilterSubmit} className="filter-bar">
        <div className="form-col">
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

        <div className="form-col-wide">
          <input
            type="text"
            className="form-control"
            placeholder="Search by lot name or address..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <Button type="submit" variant="primary">
          <Icon name="search" size={16} /> Search
        </Button>
        {(cityParam || searchParam) && (
          <Button type="button" variant="outline" onClick={handleClear}>
            <Icon name="close" size={16} /> Clear Filters
          </Button>
        )}
      </form>

      {/* Results */}
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
            cityParam || searchParam ? (
              <Button variant="secondary" onClick={handleClear}>
                Reset Search
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <p className="muted-sm mb-3">
            {count} {count === 1 ? 'facility' : 'facilities'} found
          </p>

          <div className="grid grid-cols-2 mb-4">
            {lots.map((lot) => (
              <Card key={lot.id} className="lot-card">
                <div className="flex items-center justify-between gap-2 mb-2">
                  <h3 className="card-title">{lot.name}</h3>
                  <Icon name="building" size={20} className="text-subtle" />
                </div>

                <div className="badge-row mb-2">
                  <Badge variant="info">
                    {lot.city.name} · {lot.code}
                  </Badge>
                  {lot.is_active && <Badge variant="success">Active</Badge>}
                </div>

                <p className="muted-sm flex items-center gap-2 mb-0">
                  <Icon name="mapPin" size={15} className="text-subtle" />
                  <span>
                    {lot.address_line}
                    {lot.postal_code && `, ${lot.postal_code}`}
                    {lot.state && `, ${lot.state}`}
                  </span>
                </p>

                <div className="divider-top row-between">
                  <span className="muted-sm">Parking facility</span>
                  <Link to={`/consumer/lots/${lot.id}`} className="btn btn-primary btn-sm">
                    Select &amp; Book Slot <Icon name="arrowRight" size={15} />
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