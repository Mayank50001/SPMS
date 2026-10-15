// Manager My Lots Page
import React from 'react'
import { Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import type { ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
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
      <div className="page-header">
        <div>
          <h1 className="page-title">My Parking Facilities</h1>
          <p className="page-subtitle">Facilities assigned to your manager profile for operational oversight</p>
        </div>
      </div>

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
                    <th>Facility Code</th>
                    <th>Name</th>
                    <th>Location / City</th>
                    <th>Status</th>
                    <th>Management Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((lot) => (
                    <tr key={lot.id}>
                      <td className="font-mono font-semibold" style={{ fontSize: '1rem' }}>
                        {lot.code}
                      </td>
                      <td>
                        <strong>{lot.name}</strong>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                          {lot.address_line}
                        </div>
                      </td>
                      <td>{lot.city.name} ({lot.city.code})</td>
                      <td>
                        <span className={`badge ${lot.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {lot.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <Link to={`/manager/lots/${lot.id}/occupancy`} className="btn btn-primary btn-sm">
                            Live Occupancy
                          </Link>
                          <Link to={`/manager/lots/${lot.id}/slots`} className="btn btn-outline btn-sm">
                            Slots
                          </Link>
                          <Link to={`/manager/lots/${lot.id}/tariffs`} className="btn btn-outline btn-sm">
                            Tariffs
                          </Link>
                          <Link to={`/manager/lots/${lot.id}`} className="btn btn-secondary btn-sm">
                            Facility Info
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

