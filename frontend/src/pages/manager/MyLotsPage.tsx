// Manager My Lots Page
import React from 'react'
import { Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import type { ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'

export const MyLotsPage: React.FC = () => {
  const {
    results: lots,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
  } = usePaginated<ParkingLot>('/parking-lots/')

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="My parking facilities"
        subtitle="Facilities assigned to your manager profile for operational oversight"
      />

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading facilities..." />
        ) : lots.length === 0 ? (
          <EmptyState
            title="No facilities assigned"
            message="You currently do not have any parking lots assigned. Please contact an Administrator to assign facilities to your account."
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Facility code</th>
                    <th>Name</th>
                    <th>Location</th>
                    <th>Status</th>
                    <th>Management actions</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((lot) => (
                    <tr key={lot.id}>
                      <td>
                        <span className="plate">{lot.code}</span>
                      </td>
                      <td>
                        <strong>{lot.name}</strong>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                          {lot.address_line}
                        </div>
                      </td>
                      <td>
                        {lot.city.name} ({lot.city.code})
                      </td>
                      <td>
                        <Badge variant={lot.is_active ? 'success' : 'danger'}>
                          {lot.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </td>
                      <td>
                        <div className="toolbar">
                          <Link to={`/manager/lots/${lot.id}/occupancy`} className="btn btn-primary btn-sm">
                            <Icon name="layers" size={14} /> Occupancy
                          </Link>
                          <Link to={`/manager/lots/${lot.id}/slots`} className="btn btn-outline btn-sm">
                            Slots
                          </Link>
                          <Link to={`/manager/lots/${lot.id}/tariffs`} className="btn btn-outline btn-sm">
                            Tariffs
                          </Link>
                          <Link to={`/manager/lots/${lot.id}`} className="btn btn-secondary btn-sm">
                            Facility info
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Pagination
              currentPage={page}
              totalPages={totalPages}
              totalItems={count}
              pageSize={pageSize}
              onPageChange={setPage}
              loading={loading}
            />
          </>
        )}
      </Card>
    </div>
  )
}