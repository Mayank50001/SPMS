// Slot Management Page
import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { useApi } from '../../hooks/useApi'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { ParkingSlot, SlotType, PhysicalSlotStatus, Tariff, ParkingLot } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge, SlotStatusBadge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { Modal } from '../../components/common/Modal'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'

export const SlotManagementPage: React.FC = () => {
  const { lotId } = useParams<{ lotId: string }>()

  // Fetch lot details
  const { data: lot } = useApi<ParkingLot>(lotId ? `/parking-lots/${lotId}/` : null)

  // Fetch existing tariffs to know valid slot types
  const { results: tariffs } = usePaginated<Tariff>(lotId ? `/parking-lots/${lotId}/tariffs/` : '', {
    pageSize: 50,
    skip: !lotId,
  })

  // Fetch slots in this lot
  const {
    results: slots,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<ParkingSlot>(lotId ? `/parking-lots/${lotId}/slots/` : '', {
    pageSize: 25,
    skip: !lotId,
  })

  // Add slot modal state
  const [showAddModal, setShowAddModal] = useState(false)
  const [number, setNumber] = useState('')
  const [floor, setFloor] = useState('1')
  const [slotType, setSlotType] = useState<SlotType>('REGULAR')
  const [minHours, setMinHours] = useState('1')
  const [maxHours, setMaxHours] = useState('24')
  const [status, setStatus] = useState<PhysicalSlotStatus>('AVAILABLE')

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({})

  // Status toggle state
  const [actionSlotId, setActionSlotId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const handleOpenAdd = () => {
    setNumber('')
    setFloor('1')
    setSlotType(tariffs[0]?.slot_type || 'REGULAR')
    setMinHours('1')
    setMaxHours('24')
    setStatus('AVAILABLE')
    setError(null)
    setFieldErrors({})
    setShowAddModal(true)
  }

  const handleCreateSlot = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!lotId) return
    setSaving(true)
    setError(null)
    setFieldErrors({})

    try {
      await apiFetch<ParkingSlot>(`/parking-lots/${lotId}/slots/`, {
        method: 'POST',
        body: JSON.stringify({
          number: number.trim(),
          floor: parseInt(floor, 10),
          slot_type: slotType,
          status,
          min_booking_hours: parseInt(minHours, 10),
          max_booking_hours: parseInt(maxHours, 10),
        }),
      })

      setShowAddModal(false)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.fieldErrors) setFieldErrors(err.fieldErrors)
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to create parking slot.')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleToggleStatus = async (slot: ParkingSlot) => {
    if (!lotId) return
    setActionSlotId(slot.id)
    setActionError(null)
    const newStatus: PhysicalSlotStatus =
      slot.status === 'OUT_OF_SERVICE' ? 'AVAILABLE' : 'OUT_OF_SERVICE'

    try {
      await apiFetch<ParkingSlot>(`/parking-lots/${lotId}/slots/${slot.id}/`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus }),
      })
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        setActionError(getFriendlyErrorMessage(err))
      } else {
        setActionError('Failed to update slot status.')
      }
    } finally {
      setActionSlotId(null)
    }
  }

  return (
    <div>
      <Link to={`/manager/lots/${lotId}`} className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to facility overview
      </Link>

      <PageHeader
        eyebrow="Inventory"
        title="Slot inventory"
        subtitle={
          <>
            {lot?.name} ({lot?.code}) · {count} {count === 1 ? 'bay' : 'bays'} configured
          </>
        }
        actions={
          <Button variant="primary" onClick={handleOpenAdd}>
            <Icon name="plus" size={16} /> Add slot
          </Button>
        }
      />

      {actionError && (
        <div className="alert alert-danger" role="alert">
          <span className="alert-icon text-danger">
            <Icon name="alert" size={18} />
          </span>
          <div className="alert-body">
            <p className="alert-title">Status update refused</p>
            <p>{actionError}</p>
          </div>
        </div>
      )}

      <Card>
        {loading ? (
          <LoadingSpinner message="Loading slot inventory..." />
        ) : slots.length === 0 ? (
          <EmptyState
            title="No slots in this facility"
            message="Configure parking slots and bays to enable bookings for this facility."
            action={
              <Button variant="primary" size="sm" onClick={handleOpenAdd}>
                Add first slot
              </Button>
            }
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Slot</th>
                    <th>Floor</th>
                    <th>Type</th>
                    <th>Physical status</th>
                    <th>Duration limits</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {slots.map((s) => (
                    <tr key={s.id}>
                      <td>
                        <span className="font-mono font-semibold">{s.number}</span>
                      </td>
                      <td>Floor {s.floor}</td>
                      <td>
                        <Badge variant="info">{s.slot_type}</Badge>
                      </td>
                      <td>
                        <SlotStatusBadge status={s.status} />
                      </td>
                      <td className="text-muted" style={{ fontSize: '0.8125rem' }}>
                        {s.min_booking_hours}h min · {s.max_booking_hours}h max
                      </td>
                      <td>
                        <Button
                          variant={s.status === 'OUT_OF_SERVICE' ? 'secondary' : 'outline'}
                          size="sm"
                          loading={actionSlotId === s.id}
                          disabled={s.status === 'OCCUPIED'}
                          onClick={() => handleToggleStatus(s)}
                        >
                          {s.status === 'OUT_OF_SERVICE' ? 'Put in service' : 'Take out of service'}
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

      {/* Add Slot Modal */}
      <Modal
        isOpen={showAddModal}
        title="Add parking slot"
        onClose={() => setShowAddModal(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAddModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" loading={saving} onClick={handleCreateSlot}>
              Create slot
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

        <form onSubmit={handleCreateSlot}>
          <div className="form-row">
            <div className="form-col">
              <label className="form-label">
                Slot identifier <span className="required">*</span>
              </label>
              <input
                type="text"
                required
                className={`form-control ${fieldErrors.number ? 'is-invalid' : ''}`}
                placeholder="e.g. A-101"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
              />
              {fieldErrors.number && <p className="form-error">{fieldErrors.number[0]}</p>}
            </div>

            <div className="form-col">
              <label className="form-label">
                Floor level <span className="required">*</span>
              </label>
              <input
                type="number"
                required
                className={`form-control ${fieldErrors.floor ? 'is-invalid' : ''}`}
                value={floor}
                onChange={(e) => setFloor(e.target.value)}
              />
              {fieldErrors.floor && <p className="form-error">{fieldErrors.floor[0]}</p>}
            </div>
          </div>

          <div className="form-row mt-3">
            <div className="form-col">
              <label className="form-label">
                Slot type <span className="required">*</span>
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
              <p className="form-hint">Must match an existing tariff for this facility.</p>
            </div>

            <div className="form-col">
              <label className="form-label">Initial status</label>
              <select
                className="form-control"
                value={status}
                onChange={(e) => setStatus(e.target.value as PhysicalSlotStatus)}
              >
                <option value="AVAILABLE">Available</option>
                <option value="OUT_OF_SERVICE">Out of service</option>
              </select>
            </div>
          </div>

          <div className="form-row mt-3">
            <div className="form-col">
              <label className="form-label">Min booking hours</label>
              <input
                type="number"
                min={1}
                className="form-control"
                value={minHours}
                onChange={(e) => setMinHours(e.target.value)}
              />
            </div>

            <div className="form-col">
              <label className="form-label">Max booking hours</label>
              <input
                type="number"
                min={1}
                className={`form-control ${fieldErrors.max_booking_hours ? 'is-invalid' : ''}`}
                value={maxHours}
                onChange={(e) => setMaxHours(e.target.value)}
              />
              {fieldErrors.max_booking_hours && (
                <p className="form-error">{fieldErrors.max_booking_hours[0]}</p>
              )}
            </div>
          </div>
        </form>
      </Modal>
    </div>
  )
}