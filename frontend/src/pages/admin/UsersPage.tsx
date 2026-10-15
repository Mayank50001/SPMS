// Administrator Users Management Page (D26 / D27)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { User, UserRole } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { RoleBadge } from '../../components/common/Badge'
import { Modal } from '../../components/common/Modal'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { formatDate } from '../../lib/format'

export const UsersPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const roleParam = searchParams.get('role') || ''
  const activeParam = searchParams.get('is_active') || ''
  const searchParam = searchParams.get('search') || ''

  const [roleFilter, setRoleFilter] = useState(roleParam)
  const [activeFilter, setActiveFilter] = useState(activeParam)
  const [searchFilter, setSearchFilter] = useState(searchParam)

  const {
    results: users,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<User>('/users/', {
    params: {
      role: roleParam || undefined,
      is_active: activeParam !== '' ? activeParam : undefined,
      search: searchParam || undefined,
    },
  })

  // Create User Modal
  const [showAddModal, setShowAddModal] = useState(false)
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState<'MANAGER' | 'ADMIN'>('MANAGER')
  const [password, setPassword] = useState('')

  // Edit / Role Change Modal
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [newRole, setNewRole] = useState<UserRole>('CONSUMER')
  const [newActive, setNewActive] = useState<boolean>(true)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const sp = new URLSearchParams()
    if (roleFilter) sp.set('role', roleFilter)
    if (activeFilter) sp.set('is_active', activeFilter)
    if (searchFilter.trim()) sp.set('search', searchFilter.trim())
    setSearchParams(sp)
  }

  const handleOpenAdd = () => {
    setEmail('')
    setFullName('')
    setPhone('')
    setRole('MANAGER')
    setPassword('')
    setError(null)
    setFieldErrors({})
    setShowAddModal(true)
  }

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      await apiFetch<User>('/users/', {
        method: 'POST',
        body: JSON.stringify({
          email: email.trim(),
          full_name: fullName.trim(),
          phone: phone.trim() || undefined,
          role,
          password,
        }),
      })

      setShowAddModal(false)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to create account.')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleOpenEdit = (u: User) => {
    setEditingUser(u)
    setNewRole(u.role)
    setNewActive(u.is_active ?? true)
    setError(null)
  }

  const handleUpdateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingUser) return
    setSaving(true)
    setError(null)

    try {
      await apiFetch<User>(`/users/${editingUser.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          role: newRole,
          is_active: newActive,
        }),
      })

      setEditingUser(null)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to update user profile.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">User Accounts</h1>
          <p className="page-subtitle">Manage consumer, manager, and administrator identities</p>
        </div>
        <div className="page-actions">
          <Button variant="primary" onClick={handleOpenAdd}>
            + Provision Privileged User
          </Button>
        </div>
      </div>

      {/* Filter Bar */}
      <form onSubmit={handleFilterSubmit} className="filter-bar">
        <div style={{ minWidth: '150px' }}>
          <select
            className="form-control"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
          >
            <option value="">All Roles</option>
            <option value="CONSUMER">Consumer</option>
            <option value="MANAGER">Manager</option>
            <option value="ADMIN">Administrator</option>
          </select>
        </div>

        <div style={{ minWidth: '140px' }}>
          <select
            className="form-control"
            value={activeFilter}
            onChange={(e) => setActiveFilter(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="true">Active Only</option>
            <option value="false">Suspended Only</option>
          </select>
        </div>

        <div style={{ flex: '1', minWidth: '200px' }}>
          <input
            type="text"
            className="form-control"
            placeholder="Search by name or email address..."
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
          />
        </div>

        <Button type="submit" variant="primary">
          Filter
        </Button>

        {(roleParam || activeParam || searchParam) && (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setRoleFilter('')
              setActiveFilter('')
              setSearchFilter('')
              setSearchParams({})
            }}
          >
            Clear
          </Button>
        )}
      </form>

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading user directory..." />
        ) : users.length === 0 ? (
          <EmptyState title="No users found" message="No user accounts matched the filter criteria." />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Role</th>
                    <th>Phone</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.full_name}</strong>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>{u.email}</div>
                      </td>
                      <td>
                        <RoleBadge role={u.role} />
                      </td>
                      <td>{u.phone || <span className="text-muted">—</span>}</td>
                      <td>
                        <span className={`badge ${u.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {u.is_active ? 'Active' : 'Suspended'}
                        </span>
                      </td>
                      <td>{formatDate(u.created_at)}</td>
                      <td>
                        <Button variant="outline" size="sm" onClick={() => handleOpenEdit(u)}>
                          Edit / Role
                        </Button>
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

      {/* Provision Privileged User Modal */}
      <Modal
        isOpen={showAddModal}
        title="Provision Manager or Administrator"
        onClose={() => setShowAddModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleCreateUser}>
              Create Account
            </Button>
          </>
        }
      >
        {error && (
          <div className="error-state mb-4" role="alert">
            <div className="error-icon">⚠️</div>
            <div className="error-content">
              <p className="error-message">{error}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleCreateUser}>
          <div className="form-group">
            <label className="form-label">
              Full Name <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.full_name ? 'is-invalid' : ''}`}
              placeholder="e.g. John Operator"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
            {fieldErrors.full_name && <p className="form-error">{fieldErrors.full_name[0]}</p>}
          </div>

          <div className="form-group">
            <label className="form-label">
              Email Address <span className="required">*</span>
            </label>
            <input
              type="email"
              required
              className={`form-control ${fieldErrors.email ? 'is-invalid' : ''}`}
              placeholder="operator@spms.local"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {fieldErrors.email && <p className="form-error">{fieldErrors.email[0]}</p>}
          </div>

          <div className="form-row">
            <div className="form-col">
              <label className="form-label">
                Role Authority <span className="required">*</span>
              </label>
              <select
                className="form-control"
                value={role}
                onChange={(e) => setRole(e.target.value as 'MANAGER' | 'ADMIN')}
              >
                <option value="MANAGER">Parking Manager</option>
                <option value="ADMIN">Administrator</option>
              </select>
            </div>

            <div className="form-col">
              <label className="form-label">Phone Number</label>
              <input
                type="tel"
                className="form-control"
                placeholder="+91..."
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>
          </div>

          <div className="form-group mt-2">
            <label className="form-label">
              Temporary Password <span className="required">*</span>
            </label>
            <input
              type="password"
              required
              className={`form-control ${fieldErrors.password ? 'is-invalid' : ''}`}
              placeholder="Minimum 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {fieldErrors.password && <p className="form-error">{fieldErrors.password[0]}</p>}
          </div>
        </form>
      </Modal>

      {/* Edit Role / Suspension Modal */}
      <Modal
        isOpen={editingUser !== null}
        title={`Edit User: ${editingUser?.full_name}`}
        onClose={() => setEditingUser(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditingUser(null)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleUpdateUser}>
              Save Changes
            </Button>
          </>
        }
      >
        {error && (
          <div className="error-state mb-4" role="alert">
            <div className="error-icon">⚠️</div>
            <div className="error-content">
              <h4 className="error-title">Update Refused</h4>
              <p className="error-message">{error}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleUpdateUser}>
          <div className="form-group">
            <label className="form-label">Role</label>
            <select
              className="form-control"
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as UserRole)}
            >
              <option value="CONSUMER">Consumer</option>
              <option value="MANAGER">Parking Manager</option>
              <option value="ADMIN">Administrator</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">Account Active Status</label>
            <select
              className="form-control"
              value={String(newActive)}
              onChange={(e) => setNewActive(e.target.value === 'true')}
            >
              <option value="true">Active (Permitted to sign in)</option>
              <option value="false">Suspended (Login blocked)</option>
            </select>
            <p className="form-hint">
              Per Invariant 4/D24: The system will refuse to demote or suspend the last remaining Administrator.
            </p>
          </div>
        </form>
      </Modal>
    </div>
  )
}

