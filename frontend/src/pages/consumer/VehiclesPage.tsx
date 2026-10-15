// Consumer Vehicle Management Page
import React, { useState } from 'react'
import { usePaginated } from '../../hooks/usePaginated'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { Vehicle, VehicleCreatePayload } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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
  const [deleteError, setDeleteError] = useState<string | null>(null)

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
    setDeleteError(null)
    try {
      await apiFetch(`/vehicles/${id}/`, { method: 'DELETE' })
      setDeletingId(null)
      refetch()
    } catch (err) {
      setDeleteError(getFriendlyErrorMessage(err))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="My garage"
        title="Registered vehicles"
        subtitle="Manage the license plates linked to your account"
        actions={
          <Button variant="primary" onClick={handleOpenAdd}>
            <Icon name="plus" size={16} /> Register vehicle
          </Button>
        }
      />

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading your vehicles..." />
        ) : vehicles.length === 0 ? (
          <EmptyState
            title="No vehicles registered"
            message="You need at least one vehicle before you can make a parking reservation."
            action={
              <Button variant="primary" size="sm" onClick={handleOpenAdd}>
                Register your vehicle
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>License plate</th>
                    <th>Make &amp; model</th>
                    <th>Color</th>
                    <th>Added on</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {vehicles.map((v) => (
                    <tr key={v.id}>
                      <td>
                        <span className="plate">{v.registration_number}</span>
                      </td>
                      <td>
                        {v.make || v.model ? (
                          <span>{[v.make, v.model].filter(Boolean).join(' ')}</span>
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
                          onClick={() => {
                            setDeleteError(null)
                            setDeletingId(v.id)
                          }}
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
        title="Register vehicle"
        onClose={() => setShowAddModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleCreateVehicle}>
              Save vehicle
            </Button>
          </>
        }
      >
        {error && (
          <div className="alert alert-danger" role="alert">
            <span className="alert-icon text-danger">
              <Icon name="alert" size={18} />
            </span>
            <div className="alert-body">
              <p>{error}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleCreateVehicle}>
          <p className="form-hint mb-3">
            Enter the India registration segments (example: KA-01-AB-1234).
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
              {fieldErrors.state_code && <p className="form-error">{fieldErrors.state_code[0]}</p>}
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
              {fieldErrors.rto_code && <p className="form-error">{fieldErrors.rto_code[0]}</p>}
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
              {fieldErrors.series && <p className="form-error">{fieldErrors.series[0]}</p>}
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
              {fieldErrors.unique_number && (
                <p className="form-error">{fieldErrors.unique_number[0]}</p>
              )}
            </div>
          </div>

          <div className="form-row mt-3">
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
        title="Remove vehicle"
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
              Confirm removal
            </Button>
          </>
        }
      >
        <p>Are you sure you want to remove this vehicle from your account?</p>
        {deleteError && <p className="text-danger mt-2">{deleteError}</p>}
      </Modal>
    </div>
  )
}