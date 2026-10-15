// Manager Lot Overview Page
import React from 'react'
import { useParams, Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import type { ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatDate } from '../../lib/format'

export const ManagerLotDetailsPage: React.FC = () => {
  const { lotId } = useParams<{ lotId: string }>()

  const {
    data: lot,
    loading,
    error,
    refetch,
  } = useApi<ParkingLot>(lotId ? `/parking-lots/${lotId}/` : null)

  if (loading) return <LoadingSpinner message="Loading lot details..." />
  if (error || !lot) {
    return <ErrorState error={error} title="Facility not found" onRetry={refetch} />
  }

  return (
    <div>
      <div className="mb-2">
        <Link to="/manager/lots" className="text-muted" style={{ fontSize: '0.875rem' }}>
          ← Back to Assigned Lots
        </Link>
      </div>

      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <span className="badge badge-info">{lot.code}</span>
            <span className={`badge ${lot.is_active ? 'badge-success' : 'badge-danger'}`}>
              {lot.is_active ? 'Active' : 'Inactive'}
            </span>
          </div>
          <h1 className="page-title">{lot.name}</h1>
          <p className="page-subtitle">
            📍 {lot.address_line}, {lot.city.name} {lot.postal_code}
          </p>
        </div>

        <div className="page-actions">
          <Link to={`/manager/lots/${lot.id}/occupancy`} className="btn btn-primary">
            Live Occupancy Board →
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-3 mb-4">
        <Card title="Slots & Inventory" subtitle="Configure bays and duration limits">
          <p className="text-muted mb-4" style={{ fontSize: '0.875rem' }}>
            Add new parking bays, adjust status between Available and Out of Service, and enforce duration policies.
          </p>
          <Link to={`/manager/lots/${lot.id}/slots`} className="btn btn-outline btn-sm">
            Manage Slots →
          </Link>
        </Card>

        <Card title="Pricing & Tariffs" subtitle="Hourly rates per slot category">
          <p className="text-muted mb-4" style={{ fontSize: '0.875rem' }}>
            Configure hourly rates for Regular, EV, Two-Wheeler, Compact, and Large vehicles within platform caps.
          </p>
          <Link to={`/manager/lots/${lot.id}/tariffs`} className="btn btn-outline btn-sm">
            Manage Tariffs →
          </Link>
        </Card>

        <Card title="Lot Bookings" subtitle="Filter bookings for this facility">
          <p className="text-muted mb-4" style={{ fontSize: '0.875rem' }}>
            View consumer arrival schedules, process gate check-in / check-out, and monitor overstay fees.
          </p>
          <Link to={`/manager/bookings?lot=${lot.id}`} className="btn btn-outline btn-sm">
            View Bookings →
          </Link>
        </Card>
      </div>

      <Card title="Facility Metadata">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          <div className="flex justify-between">
            <span className="text-muted">Facility Code</span>
            <span className="font-mono font-semibold">{lot.code}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">City Code / Name</span>
            <span>{lot.city.name} ({lot.city.code})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Registered State</span>
            <span>{lot.state || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Postal Code</span>
            <span>{lot.postal_code || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-muted">Operational Since</span>
            <span>{formatDate(lot.created_at)}</span>
          </div>
        </div>
      </Card>
    </div>
  )
}

