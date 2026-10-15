// Administrator Parking Lots Management & Assignment Page
import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ParkingLot, City, User } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'

export const AdminLotsPage: React.FC = () => {
  const {
    results: lots,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<ParkingLot>('/parking-lots/')

  // Fetch cities (bare array per D66)
  const { data: cities, refetch: refetchCities } = useApi<City[]>('/cities/')

  // Fetch managers for assignment
  const { results: managers } = usePaginated<User>('/users/', {
    params: { role: 'MANAGER' },
    pageSize: 100,
  })

  // Create Lot Modal
  const [showAddModal, setShowAddModal] = useState(false)
  const [cityCode, setCityCode] = useState('')
  const [number, setNumber] = useState('')
  const [name, setName] = useState('')
  const [addressLine, setAddressLine] = useState('')
  const [state, setState] = useState('')
  const [postalCode, setPostalCode] = useState('')
  const [managerId, setManagerId] = useState<number | ''>('')
  const [isActive, setIsActive] = useState(true)

  // Quick City Creation Modal
  const [showCityModal, setShowCityModal] = useState(false)
  const [newCityCode, setNewCityCode] = useState('')
  const [newCityName, setNewCityName] = useState('')
  const [citySaving, setCitySaving] = useState(false)

  // Edit Lot Modal
  const [editingLot, setEditingLot] = useState<ParkingLot | null>(null)
  const [editName, setEditName] = useState('')
  const [editAddress, setEditAddress] = useState('')
  const [editManagerId, setEditManagerId] = useState<number | ''>('')
  const [editIsActive, setEditIsActive] = useState(true)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const handleOpenAdd = () => {
    setCityCode(cities?.[0]?.code || '')
    setNumber('1')
    setName('')
    setAddressLine('')
    setState('')
    setPostalCode('')
    setManagerId('')
    setIsActive(true)
    setError(null)
    setFieldErrors({})
    setShowAddModal(true)
  }

  const handleCreateCity = async (e: React.FormEvent) => {
    e.preventDefault()
    setCitySaving(true)
    try {
      await apiFetch<City>('/cities/', {
        method: 'POST',
        body: JSON.stringify({
          code: newCityCode.trim().toUpperCase(),
          name: newCityName.trim(),
        }),
      })
      await refetchCities()
      setCityCode(newCityCode.trim().toUpperCase())
      setShowCityModal(false)
      setNewCityCode('')
      setNewCityName('')
    } catch (err) {
      alert(getFriendlyErrorMessage(err))
    } finally {
      setCitySaving(false)
    }
  }

  const handleCreateLot = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      await apiFetch<ParkingLot>('/parking-lots/', {
        method: 'POST',
        body: JSON.stringify({
          city_code: cityCode,
          number: parseInt(number, 10),
          name: name.trim(),
          address_line: addressLine.trim(),
          state: state.trim() || undefined,
          postal_code: postalCode.trim() || undefined,
          manager: managerId !== '' ? managerId : null,
          is_active: isActive,
        }),
      })

      setShowAddModal(false)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to create parking lot.')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleOpenEdit = (lot: ParkingLot) => {
    setEditingLot(lot)
    setEditName(lot.name)
    setEditAddress(lot.address_line)
    setEditManagerId(lot.manager ?? '')
    setEditIsActive(lot.is_active)
    setError(null)
    setFieldErrors({})
  }

  const handleUpdateLot = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingLot) return
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      await apiFetch<ParkingLot>(`/parking-lots/${editingLot.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          name: editName.trim(),
          address_line: editAddress.trim(),
          manager: editManagerId !== '' ? editManagerId : null,
          is_active: editIsActive,
        }),
      })

      setEditingLot(null)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to update facility.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Parking Facilities</h1>
          <p className="page-subtitle">Configure parking lots, geographic codes, and manager assignments</p>
        </div>
        <div className="page-actions">
          <Button variant="secondary" onClick={() => setShowCityModal(true)}>
            + Add City
          </Button>
          <Button variant="primary" onClick={handleOpenAdd}>
            + Add Parking Lot
          </Button>
        </div>
      </div>

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading parking facilities..." />
        ) : lots.length === 0 ? (
          <EmptyState
            title="No parking lots"
            message="Get started by creating your first parking facility."
            action={
              <Button variant="primary" size="sm" onClick={handleOpenAdd}>
                Add Facility
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Facility Code</th>
                    <th>Name</th>
                    <th>City / Address</th>
                    <th>Assigned Manager</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {lots.map((lot) => {
                    const managerUser = managers.find((m) => m.id === lot.manager)
                    return (
                      <tr key={lot.id}>
                        <td className="font-mono font-semibold" style={{ fontSize: '1rem' }}>
                          {lot.code}
                        </td>
                        <td>
                          <strong>{lot.name}</strong>
                          <div className="text-muted" style={{ fontSize: '0.75rem' }}>ID #{lot.id}</div>
                        </td>
                        <td>
                          <div>{lot.city.name} ({lot.city.code})</div>
                          <div className="text-muted" style={{ fontSize: '0.75rem' }}>{lot.address_line}</div>
                        </td>
                        <td>
                          {managerUser ? (
                            <div>
                              <strong>{managerUser.full_name}</strong>
                              <div className="text-muted" style={{ fontSize: '0.75rem' }}>{managerUser.email}</div>
                            </div>
                          ) : (
                            <span className="text-muted">Unassigned</span>
                          )}
                        </td>
                        <td>
                          <span className={`badge ${lot.is_active ? 'badge-success' : 'badge-danger'}`}>
                            {lot.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '0.35rem' }}>
                            <Button variant="outline" size="sm" onClick={() => handleOpenEdit(lot)}>
                              Edit / Assign
                            </Button>
                            <Link to={`/manager/lots/${lot.id}/slots`} className="btn btn-secondary btn-sm">
                              Slots
                            </Link>
                            <Link to={`/manager/lots/${lot.id}/tariffs`} className="btn btn-secondary btn-sm">
                              Tariffs
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
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

      {/* Add Lot Modal */}
      <Modal
        isOpen={showAddModal}
        title="Add Parking Facility"
        onClose={() => setShowAddModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleCreateLot}>
              Save Facility
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

        <form onSubmit={handleCreateLot}>
          <div className="form-row">
            <div className="form-col">
              <label className="form-label">
                City <span className="required">*</span>
              </label>
              <select
                className={`form-control ${fieldErrors.city_code ? 'is-invalid' : ''}`}
                value={cityCode}
                onChange={(e) => setCityCode(e.target.value)}
                required
              >
                {cities?.map((c) => (
                  <option key={c.id} value={c.code}>
                    {c.name} ({c.code})
                  </option>
                ))}
              </select>
              {fieldErrors.city_code && <p className="form-error">{fieldErrors.city_code[0]}</p>}
            </div>

            <div className="form-col" style={{ maxWidth: '120px' }}>
              <label className="form-label">
                Lot Number <span className="required">*</span>
              </label>
              <input
                type="number"
                min={1}
                required
                className={`form-control ${fieldErrors.number ? 'is-invalid' : ''}`}
                placeholder="1"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
              />
              {fieldErrors.number && <p className="form-error">{fieldErrors.number[0]}</p>}
            </div>
          </div>

          <div className="form-group mt-2">
            <label className="form-label">
              Facility Name <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.name ? 'is-invalid' : ''}`}
              placeholder="e.g. Central Station Multi-Level"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            {fieldErrors.name && <p className="form-error">{fieldErrors.name[0]}</p>}
          </div>

          <div className="form-group">
            <label className="form-label">
              Address Line <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.address_line ? 'is-invalid' : ''}`}
              placeholder="e.g. 12 Station Road"
              value={addressLine}
              onChange={(e) => setAddressLine(e.target.value)}
            />
            {fieldErrors.address_line && <p className="form-error">{fieldErrors.address_line[0]}</p>}
          </div>

          <div className="form-row">
            <div className="form-col">
              <label className="form-label">State</label>
              <input
                type="text"
                className="form-control"
                placeholder="Karnataka"
                value={state}
                onChange={(e) => setState(e.target.value)}
              />
            </div>

            <div className="form-col">
              <label className="form-label">Postal Code</label>
              <input
                type="text"
                className="form-control"
                placeholder="560001"
                value={postalCode}
                onChange={(e) => setPostalCode(e.target.value)}
              />
            </div>
          </div>

          <div className="form-row mt-2">
            <div className="form-col">
              <label className="form-label">Assign Manager</label>
              <select
                className="form-control"
                value={managerId}
                onChange={(e) => setManagerId(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">None (Unassigned)</option>
                {managers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.full_name} ({m.email})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-col">
              <label className="form-label">Active Status</label>
              <select
                className="form-control"
                value={String(isActive)}
                onChange={(e) => setIsActive(e.target.value === 'true')}
              >
                <option value="true">Active (Accepts Bookings)</option>
                <option value="false">Inactive</option>
              </select>
            </div>
          </div>
        </form>
      </Modal>

      {/* Edit Lot Modal */}
      <Modal
        isOpen={editingLot !== null}
        title={`Edit Facility: ${editingLot?.code}`}
        onClose={() => setEditingLot(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditingLot(null)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleUpdateLot}>
              Save Changes
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

        <form onSubmit={handleUpdateLot}>
          <div className="form-group">
            <label className="form-label">
              Facility Name <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className="form-control"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">
              Address Line <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className="form-control"
              value={editAddress}
              onChange={(e) => setEditAddress(e.target.value)}
            />
          </div>

          <div className="form-row">
            <div className="form-col">
              <label className="form-label">Assign Manager</label>
              <select
                className="form-control"
                value={editManagerId}
                onChange={(e) => setEditManagerId(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">None (Unassigned)</option>
                {managers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.full_name} ({m.email})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-col">
              <label className="form-label">Active Status</label>
              <select
                className="form-control"
                value={String(editIsActive)}
                onChange={(e) => setEditIsActive(e.target.value === 'true')}
              >
                <option value="true">Active</option>
                <option value="false">Inactive</option>
              </select>
            </div>
          </div>
        </form>
      </Modal>

      {/* Add City Modal */}
      <Modal
        isOpen={showCityModal}
        title="Register New City"
        onClose={() => setShowCityModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCityModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={citySaving} onClick={handleCreateCity}>
              Add City
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreateCity}>
          <div className="form-group">
            <label className="form-label">
              City Code (2-4 uppercase letters) <span className="required">*</span>
            </label>
            <input
              type="text"
              maxLength={4}
              required
              className="form-control"
              placeholder="e.g. BLR, DEL, MUM"
              value={newCityCode}
              onChange={(e) => setNewCityCode(e.target.value.toUpperCase())}
            />
          </div>

          <div className="form-group">
            <label className="form-label">
              City Name <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className="form-control"
              placeholder="e.g. Bengaluru"
              value={newCityName}
              onChange={(e) => setNewCityName(e.target.value)}
            />
          </div>
        </form>
      </Modal>
    </div>
  )
}

