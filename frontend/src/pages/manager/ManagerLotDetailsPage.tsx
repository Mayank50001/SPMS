// Manager Lot Overview Page
import React from 'react'
import { useParams, Link } from 'react-router-dom'
import { useApi } from '../../hooks/useApi'
import type { ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
      <Link to="/manager/lots" className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to assigned lots
      </Link>

      <PageHeader
        eyebrow={
          <span className="badge-row">
            <Badge variant="info">{lot.code}</Badge>
            <Badge variant={lot.is_active ? 'success' : 'danger'}>
              {lot.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </span>
        }
        title={lot.name}
        subtitle={
          <span className="flex items-center gap-2">
            <Icon name="mapPin" size={15} className="text-subtle" />
            <span>
              {lot.address_line}, {lot.city.name}
              {lot.postal_code ? ` ${lot.postal_code}` : ''}
            </span>
          </span>
        }
        actions={
          <Link to={`/manager/lots/${lot.id}/occupancy`} className="btn btn-primary btn-md">
            <Icon name="layers" size={16} /> Live occupancy board
          </Link>
        }
      />

      <div className="grid grid-cols-3 mb-4">
        <Card>
          <div className="feature-icon">
            <Icon name="grid" size={22} />
          </div>
          <h3 className="card-title">Slots &amp; inventory</h3>
          <p className="muted-sm" style={{ marginBottom: '1rem' }}>
            Add parking bays, switch status between Available and Out of Service, and enforce
            duration policies.
          </p>
          <Link to={`/manager/lots/${lot.id}/slots`} className="btn btn-outline btn-sm">
            Manage slots <Icon name="arrowRight" size={14} />
          </Link>
        </Card>

        <Card>
          <div className="feature-icon success">
            <Icon name="wallet" size={22} />
          </div>
          <h3 className="card-title">Pricing &amp; tariffs</h3>
          <p className="muted-sm" style={{ marginBottom: '1rem' }}>
            Configure hourly rates for Regular, EV, Two-Wheeler, Compact and Large vehicles within
            platform caps.
          </p>
          <Link to={`/manager/lots/${lot.id}/tariffs`} className="btn btn-outline btn-sm">
            Manage tariffs <Icon name="arrowRight" size={14} />
          </Link>
        </Card>

        <Card>
          <div className="feature-icon info">
            <Icon name="ticket" size={22} />
          </div>
          <h3 className="card-title">Lot bookings</h3>
          <p className="muted-sm" style={{ marginBottom: '1rem' }}>
            Review arrival schedules, run gate check-in / check-out, and monitor overstay fees.
          </p>
          <Link to={`/manager/bookings?lot=${lot.id}`} className="btn btn-outline btn-sm">
            View bookings <Icon name="arrowRight" size={14} />
          </Link>
        </Card>
      </div>

      <Card title="Facility metadata" subtitle="Registry details for this facility">
        <div className="info-list">
          <div className="info-row">
            <span className="info-label">Facility code</span>
            <span className="info-value font-mono">{lot.code}</span>
          </div>
          <div className="info-row">
            <span className="info-label">City</span>
            <span className="info-value">
              {lot.city.name} ({lot.city.code})
            </span>
          </div>
          <div className="info-row">
            <span className="info-label">Registered state</span>
            <span className="info-value">{lot.state || '—'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Postal code</span>
            <span className="info-value">{lot.postal_code || '—'}</span>
          </div>
          <div className="info-row">
            <span className="info-label">Operational since</span>
            <span className="info-value">{formatDate(lot.created_at)}</span>
          </div>
        </div>
      </Card>
    </div>
  )
}