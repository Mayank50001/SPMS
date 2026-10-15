// Consumer Vehicle Management Page
import React, { useState } from 'react'
import { usePaginated } from '../../hooks/usePaginated'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { Vehicle, VehicleCreatePayload } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { formatDate } from '../../lib/format'

export const VehiclesPage: React.FC = () => {
  const {
    results: vehicles,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<Vehicle>('/vehicles/')

  const [showAddModal, setShowAddModal] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  // Form fields
  const [stateCode, setStateCode] = useState('KA')
  const [rtoCode, setRtoCode] = useState('')
  const [series, setSeries] = useState('')
  const [uniqueNumber, setUniqueNumber] = useState('')
  const [make, setMake] = useState('')
  const [model, setModel] = useState('')
  const [color, setColor] = useState('')

  // Delete state
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)

  const handleOpenAdd = () => {
    setStateCode('KA')
    setRtoCode('')
    setSeries('')
    setUniqueNumber('')
    setMake('')
    setModel('')
    setColor('')
    setError(null)
    setFieldErrors({})
    setShowAddModal(true)
  }

  const handleCreateVehicle = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})

    const payload: VehicleCreatePayload = {
      state_code: stateCode.trim().toUpperCase(),
      rto_code: rtoCode.trim().padStart(2, '0'),
      series: series.trim().toUpperCase(),
      unique_number: uniqueNumber.trim().padStart(4, '0'),
      make: make.trim() || undefined,
      model: model.trim() || undefined,
      color: color.trim() || undefined,
    }

    try {
      await apiFetch<Vehicle>('/vehicles/', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setShowAddModal(false)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to register vehicle.')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteVehicle = async (id: number) => {
    setDeleting(true)
    try {
      await apiFetch(`/vehicles/${id}/`, { method: 'DELETE' })
      setDeletingId(null)
      refetch()
    } catch (err) {
      alert(getFriendlyErrorMessage(err))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Registered Vehicles</h1>
          <p className="page-subtitle">Manage license plates associated with your account</p>
        </div>
        <div className="page-actions">
          <Button variant="primary" onClick={handleOpenAdd}>
            + Register New Vehicle
          </Button>
        </div>
      </div>

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading your vehicles..." />
        ) : vehicles.length === 0 ? (
          <EmptyState
            title="No vehicles registered"
            message="You must add at least one vehicle to make parking reservations."
            action={
              <Button variant="primary" size="sm" onClick={handleOpenAdd}>
                Register Your Vehicle
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>License Plate</th>
                    <th>Make & Model</th>
                    <th>Color</th>
                    <th>Added On</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {vehicles.map((v) => (
                    <tr key={v.id}>
                      <td className="font-mono font-semibold" style={{ fontSize: '1rem' }}>
                        {v.registration_number}
                      </td>
                      <td>
                        {v.make || v.model ? (
                          <span>{v.make} {v.model}</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td>{v.color || <span className="text-muted">—</span>}</td>
                      <td>{formatDate(v.created_at)}</td>
                      <td>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => setDeletingId(v.id)}
                        >
                          Delete
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

      {/* Add Vehicle Modal */}
      <Modal
        isOpen={showAddModal}
        title="Register Vehicle"
        onClose={() => setShowAddModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleCreateVehicle}>
              Save Vehicle
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

        <form onSubmit={handleCreateVehicle}>
          <p className="text-muted" style={{ fontSize: '0.8125rem', marginBottom: '0.75rem' }}>
            Provide India registration segments (e.g. KA-01-AB-1234)
          </p>

          <div className="form-row">
            <div className="form-col" style={{ maxWidth: '100px' }}>
              <label className="form-label">State</label>
              <input
                type="text"
                maxLength={2}
                required
                className={`form-control ${fieldErrors.state_code ? 'is-invalid' : ''}`}
                placeholder="KA"
                value={stateCode}
                onChange={(e) => setStateCode(e.target.value.toUpperCase())}
              />
            </div>

            <div className="form-col" style={{ maxWidth: '90px' }}>
              <label className="form-label">RTO</label>
              <input
                type="text"
                maxLength={2}
                required
                className={`form-control ${fieldErrors.rto_code ? 'is-invalid' : ''}`}
                placeholder="01"
                value={rtoCode}
                onChange={(e) => setRtoCode(e.target.value)}
              />
            </div>

            <div className="form-col" style={{ maxWidth: '110px' }}>
              <label className="form-label">Series</label>
              <input
                type="text"
                maxLength={3}
                required
                className={`form-control ${fieldErrors.series ? 'is-invalid' : ''}`}
                placeholder="AB"
                value={series}
                onChange={(e) => setSeries(e.target.value.toUpperCase())}
              />
            </div>

            <div className="form-col">
              <label className="form-label">Number</label>
              <input
                type="text"
                maxLength={4}
                required
                className={`form-control ${fieldErrors.unique_number ? 'is-invalid' : ''}`}
                placeholder="1234"
                value={uniqueNumber}
                onChange={(e) => setUniqueNumber(e.target.value)}
              />
            </div>
          </div>

          <div className="form-row mt-2">
            <div className="form-col">
              <label className="form-label">Make (optional)</label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. Maruti, Hyundai"
                value={make}
                onChange={(e) => setMake(e.target.value)}
              />
            </div>

            <div className="form-col">
              <label className="form-label">Model (optional)</label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. Swift, i20"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
            </div>

            <div className="form-col">
              <label className="form-label">Color (optional)</label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. White, Silver"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
            </div>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={deletingId !== null}
        title="Remove Vehicle"
        onClose={() => setDeletingId(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setDeletingId(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={deleting}
              onClick={() => deletingId && handleDeleteVehicle(deletingId)}
            >
              Confirm Removal
            </Button>
          </>
        }
      >
        <p>Are you sure you want to remove this vehicle from your account?</p>
      </Modal>
    </div>
  )
}

