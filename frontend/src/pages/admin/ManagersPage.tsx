// Administrator Managers Overview Page
import React from 'react'
import { Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import type { User } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
      <PageHeader
        eyebrow="Governance"
        title="Facility managers"
        subtitle="Roster of operational parking facility managers"
        actions={
          <>
            <Link to="/admin/users" className="btn btn-primary btn-md">
              <Icon name="plus" size={16} /> Provision manager
            </Link>
            <Link to="/admin/lots" className="btn btn-outline btn-md">
              <Icon name="building" size={16} /> Assign lots
            </Link>
          </>
        }
      />

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
                Provision manager
              </Link>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Manager name</th>
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
                        <Badge variant={m.is_active ? 'success' : 'danger'}>
                          {m.is_active ? 'Active' : 'Suspended'}
                        </Badge>
                      </td>
                      <td>{formatDate(m.created_at)}</td>
                      <td>
                        <Link to="/admin/lots" className="btn btn-outline btn-sm">
                          Manage facilities <Icon name="arrowRight" size={14} />
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