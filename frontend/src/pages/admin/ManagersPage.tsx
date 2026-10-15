// Administrator Managers Overview Page
import React from 'react'
import { Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import type { User } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { formatDate } from '../../lib/format'

export const ManagersPage: React.FC = () => {
  const {
    results: managers,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    error,
    refetch,
    setPage,
  } = usePaginated<User>('/users/', {
    params: { role: 'MANAGER' },
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Facility Managers</h1>
          <p className="page-subtitle">Roster of operational parking facility managers</p>
        </div>
        <div className="page-actions">
          <Link to="/admin/users" className="btn btn-primary">
            + Provision New Manager
          </Link>
          <Link to="/admin/lots" className="btn btn-secondary">
            Assign Lots
          </Link>
        </div>
      </div>

      <Card>
        {error ? (
          <ErrorState error={error} title="Failed to load managers" onRetry={refetch} />
        ) : loading ? (
          <LoadingSpinner message="Loading managers..." />
        ) : managers.length === 0 ? (
          <EmptyState
            title="No managers registered"
            message="Provision a user with the MANAGER role to assign facility operations."
            action={
              <Link to="/admin/users" className="btn btn-primary btn-sm">
                Provision Manager
              </Link>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Manager Name</th>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th>Facilities</th>
                  </tr>
                </thead>
                <tbody>
                  {managers.map((m) => (
                    <tr key={m.id}>
                      <td>
                        <strong>{m.full_name}</strong>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>ID #{m.id}</div>
                      </td>
                      <td>{m.email}</td>
                      <td>
                        <span className={`badge ${m.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {m.is_active ? 'Active' : 'Suspended'}
                        </span>
                      </td>
                      <td>{formatDate(m.created_at)}</td>
                      <td>
                        <Link to="/admin/lots" className="btn btn-outline btn-sm">
                          Manage Facilities →
                        </Link>
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

