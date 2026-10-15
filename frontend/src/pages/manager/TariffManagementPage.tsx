// Tariff (Pricing) Management Page
import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { Tariff, SlotType, BusinessRules, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { Modal } from '../../components/common/Modal'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { formatMoney } from '../../lib/format'

export const TariffManagementPage: React.FC = () => {
  const { lotId } = useParams<{ lotId: string }>()

  // Fetch lot details
  const { data: lot } = useApi<ParkingLot>(lotId ? `/parking-lots/${lotId}/` : null)

  // Fetch platform business rules for cap guidance
  const { data: rules } = useApi<BusinessRules>('/business-rules/')

  // Fetch existing tariffs
  const {
    results: tariffs,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<Tariff>(lotId ? `/parking-lots/${lotId}/tariffs/` : '', {
    pageSize: 20,
    skip: !lotId,
  })

  // Add tariff modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [slotType, setSlotType] = useState<SlotType>('REGULAR')
  const [hourlyRate, setHourlyRate] = useState('40.00')

  // Edit tariff modal state
  const [editingTariff, setEditingTariff] = useState<Tariff | null>(null)
  const [editRate, setEditRate] = useState('')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  const handleOpenAdd = () => {
    setSlotType('REGULAR')
    setHourlyRate('40.00')
    setError(null)
    setFieldErrors({})
    setShowAddModal(true)
  }

  const handleCreateTariff = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!lotId) return
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      await apiFetch<Tariff>(`/parking-lots/${lotId}/tariffs/`, {
        method: 'POST',
        body: JSON.stringify({
          slot_type: slotType,
          hourly_rate: hourlyRate,
        }),
      })

      setShowAddModal(false)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to create tariff rate.')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleOpenEdit = (t: Tariff) => {
    setEditingTariff(t)
    setEditRate(t.hourly_rate)
    setError(null)
    setFieldErrors({})
  }

  const handleUpdateTariff = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!lotId || !editingTariff) return
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      await apiFetch<Tariff>(`/parking-lots/${lotId}/tariffs/${editingTariff.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({
          hourly_rate: editRate,
        }),
      })

      setEditingTariff(null)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to update tariff rate.')
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <Link to={`/manager/lots/${lotId}`} className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to facility overview
      </Link>

      <PageHeader
        eyebrow="Pricing"
        title="Tariffs &amp; pricing"
        subtitle={
          <>
            {lot?.name} ({lot?.code}) · Hourly pricing per slot category
          </>
        }
        actions={
          <Button variant="primary" onClick={handleOpenAdd}>
            <Icon name="plus" size={16} /> Add tariff rate
          </Button>
        }
      />

      {rules && (
        <div className="alert alert-info">
          <span className="alert-icon text-primary">
            <Icon name="info" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Platform pricing policy</p>
            <p>
              The maximum allowed hourly rate across all facilities is{' '}
              <strong>{formatMoney(rules.max_hourly_rate)}</strong>. Tariffs configured above this
              limit will be rejected.
            </p>
          </div>
        </div>
      )}

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading tariffs..." />
        ) : tariffs.length === 0 ? (
          <EmptyState
            title="No tariffs defined"
            message="Slots cannot be created or booked without a configured tariff rate for their slot type."
            action={
              <Button variant="primary" size="sm" onClick={handleOpenAdd}>
                Add first tariff
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Slot category</th>
                    <th>Identifier</th>
                    <th>Hourly rate</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tariffs.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <strong>{t.slot_type_label || t.slot_type}</strong>
                      </td>
                      <td>
                        <Badge variant="neutral">{t.slot_type}</Badge>
                      </td>
                      <td className="font-semibold" style={{ fontSize: '1rem' }}>
                        {formatMoney(t.hourly_rate)} / hr
                      </td>
                      <td>
                        <Button variant="outline" size="sm" onClick={() => handleOpenEdit(t)}>
                          Edit rate
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

      {/* Add Tariff Modal */}
      <Modal
        isOpen={showAddModal}
        title="Add pricing tariff"
        onClose={() => setShowAddModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleCreateTariff}>
              Save tariff
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

        <form onSubmit={handleCreateTariff}>
          <div className="form-group">
            <label className="form-label">
              Slot type category <span className="required">*</span>
            </label>
            <select
              className="form-control"
              value={slotType}
              onChange={(e) => setSlotType(e.target.value as SlotType)}
            >
              <option value="REGULAR">Regular</option>
              <option value="COMPACT">Compact</option>
              <option value="LARGE">Large</option>
              <option value="TWO_WHEELER">Two-Wheeler</option>
              <option value="EV">Electric Vehicle (EV)</option>
            </select>
          </div>

          <div className="form-group">
            <label className="form-label">
              Hourly rate (INR) <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.hourly_rate ? 'is-invalid' : ''}`}
              placeholder="40.00"
              value={hourlyRate}
              onChange={(e) => setHourlyRate(e.target.value)}
            />
            {fieldErrors.hourly_rate && <p className="form-error">{fieldErrors.hourly_rate[0]}</p>}
            <p className="form-hint">Decimal string representation (e.g. 50.00).</p>
          </div>
        </form>
      </Modal>

      {/* Edit Tariff Modal */}
      <Modal
        isOpen={editingTariff !== null}
        title={`Edit tariff: ${editingTariff?.slot_type_label || editingTariff?.slot_type}`}
        onClose={() => setEditingTariff(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditingTariff(null)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleUpdateTariff}>
              Update rate
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

        <form onSubmit={handleUpdateTariff}>
          <div className="form-group mb-0">
            <label className="form-label">
              Hourly rate (INR) <span className="required">*</span>
            </label>
            <input
              type="text"
              required
              className={`form-control ${fieldErrors.hourly_rate ? 'is-invalid' : ''}`}
              value={editRate}
              onChange={(e) => setEditRate(e.target.value)}
            />
            {fieldErrors.hourly_rate && <p className="form-error">{fieldErrors.hourly_rate[0]}</p>}
          </div>
        </form>
      </Modal>
    </div>
  )
}