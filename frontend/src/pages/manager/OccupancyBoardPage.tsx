// Live Occupancy Board with WebSocket & HTTP polling fallback (Phase 6 / D71 / D72)
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiFetch, getStoredAccessToken } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { OccupancyBoard, OccupancyBoardSlot, PhysicalSlotStatus } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Modal } from '../../components/common/Modal'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { ErrorState } from '../../components/common/ErrorState'
import { formatDateTime } from '../../lib/format'

export const OccupancyBoardPage: React.FC = () => {
  const { lotId } = useParams<{ lotId: string }>()

  const [board, setBoard] = useState<OccupancyBoard | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState(false)

  // Selected slot for manual physical occupancy mark
  const [selectedSlot, setSelectedSlot] = useState<OccupancyBoardSlot | null>(null)
  const [marking, setMarking] = useState(false)
  const [markError, setMarkError] = useState<string | null>(null)

  const socketRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  // HTTP board fetch
  const fetchBoardHttp = useCallback(async () => {
    if (!lotId) return
    try {
      const data = await apiFetch<OccupancyBoard>(`/parking-lots/${lotId}/occupancy/`)
      setBoard(data)
      setError(null)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(getFriendlyErrorMessage(err))
      } else {
        setError('Failed to load occupancy board.')
      }
    } finally {
      setLoading(false)
    }
  }, [lotId])

  // Initial HTTP fetch
  useEffect(() => {
    fetchBoardHttp()
  }, [fetchBoardHttp])

  // WebSocket Live Connection
  useEffect(() => {
    if (!lotId) return

    let isMounted = true
    let retryDelay = 2000

    const connectWebSocket = () => {
      const token = getStoredAccessToken()
      if (!token) return

      // Connect via current origin or direct dev backend
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      // Use the vite /ws proxy or backend direct
      const wsUrl = `${protocol}//${window.location.host}/ws/parking-lots/${lotId}/occupancy/?token=${encodeURIComponent(token)}`

      const ws = new WebSocket(wsUrl)
      socketRef.current = ws

      ws.onopen = () => {
        if (!isMounted) return
        setWsConnected(true)
        retryDelay = 2000
      }

      ws.onmessage = (event) => {
        if (!isMounted) return
        try {
          const payload = JSON.parse(event.data)
          if (payload.type === 'occupancy' && payload.board) {
            setBoard(payload.board)
          }
        } catch {
          // Ignore unparseable frames
        }
      }

      ws.onclose = (event) => {
        if (!isMounted) return
        setWsConnected(false)

        // Do not auto-reconnect on fatal auth errors
        if (event.code === 4401 || event.code === 4403) {
          setError(
            event.code === 4403
              ? 'Access denied: Facility is not assigned to your account.'
              : 'Session expired for live updates. Please log in again.'
          )
          return
        }

        // Reconnect with backoff
        reconnectTimeoutRef.current = window.setTimeout(() => {
          if (isMounted) {
            retryDelay = Math.min(retryDelay * 1.5, 30000)
            connectWebSocket()
          }
        }, retryDelay)
      }

      ws.onerror = () => {
        // Will close and trigger backoff
      }
    }

    connectWebSocket()

    // Backup HTTP poll every 15 seconds if WebSocket is disconnected
    const pollInterval = setInterval(() => {
      if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
        fetchBoardHttp()
      }
    }, 15000)

    return () => {
      isMounted = false
      clearInterval(pollInterval)
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      if (socketRef.current) socketRef.current.close()
    }
  }, [lotId, fetchBoardHttp])

  // Manual physical toggle action
  const handleMarkOccupancy = async (newStatus: PhysicalSlotStatus) => {
    if (!lotId || !selectedSlot) return
    setMarking(true)
    setMarkError(null)

    try {
      await apiFetch(`/parking-lots/${lotId}/slots/${selectedSlot.id}/occupancy/`, {
        method: 'POST',
        body: JSON.stringify({ status: newStatus }),
      })

      setSelectedSlot(null)
      fetchBoardHttp()
    } catch (err) {
      if (err instanceof ApiError) {
        setMarkError(getFriendlyErrorMessage(err))
      } else {
        setMarkError('Failed to update slot physical status.')
      }
    } finally {
      setMarking(false)
    }
  }

  if (loading) return <LoadingSpinner message="Connecting to live occupancy board..." />
  if (error && !board) {
    return <ErrorState error={error} title="Occupancy board error" onRetry={fetchBoardHttp} />
  }

  return (
    <div>
      <div className="mb-2">
        <Link to={`/manager/lots/${lotId}`} className="text-muted" style={{ fontSize: '0.875rem' }}>
          ← Back to Facility
        </Link>
      </div>

      <div className="page-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.25rem' }}>
            <h1 className="page-title">{board?.lot.name || 'Parking Facility'}</h1>
            <span className={`badge ${wsConnected ? 'badge-success' : 'badge-warning'}`}>
              {wsConnected ? '🟢 Live WebSocket' : '🟡 Polling (HTTP)'}
            </span>
          </div>
          <p className="page-subtitle">
            Facility: {board?.lot.code} · Live Bay Status & In-Progress Sessions
          </p>
        </div>

        <div className="page-actions">
          <Button variant="outline" size="sm" onClick={fetchBoardHttp}>
            ↻ Sync Board
          </Button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-4 mb-4">
        <div className="stat-card">
          <div className="stat-label">Total Bays</div>
          <div className="stat-value">{board?.summary.total ?? 0}</div>
          <div className="stat-meta">Configured slot capacity</div>
        </div>

        <div className="stat-card" style={{ borderColor: 'var(--success-border)' }}>
          <div className="stat-label" style={{ color: 'var(--success)' }}>Available Bays</div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>
            {board?.summary.available ?? 0}
          </div>
          <div className="stat-meta">Free for parking</div>
        </div>

        <div className="stat-card" style={{ borderColor: 'var(--warning-border)' }}>
          <div className="stat-label" style={{ color: 'var(--warning)' }}>Occupied Bays</div>
          <div className="stat-value" style={{ color: 'var(--warning)' }}>
            {board?.summary.occupied ?? 0}
          </div>
          <div className="stat-meta">Physically in-use</div>
        </div>

        <div className="stat-card" style={{ borderColor: 'var(--danger-border)' }}>
          <div className="stat-label" style={{ color: 'var(--danger)' }}>Out of Service</div>
          <div className="stat-value" style={{ color: 'var(--danger)' }}>
            {board?.summary.out_of_service ?? 0}
          </div>
          <div className="stat-meta">Maintenance / closed</div>
        </div>
      </div>

      {/* Bay Visual Grid */}
      <Card
        title="Parking Bay Layout"
        subtitle="Click any bay to view in-progress reservation or override physical occupancy"
      >
        <div className="slots-grid">
          {board?.slots.map((slot) => {
            const isOccupied = slot.status === 'OCCUPIED'
            const isOutOfService = slot.status === 'OUT_OF_SERVICE'
            const bayClass = isOccupied
              ? 'bay-occupied'
              : isOutOfService
              ? 'bay-out-of-service'
              : 'bay-available'

            return (
              <div
                key={slot.id}
                className={`slot-tile ${bayClass}`}
                onClick={() => setSelectedSlot(slot)}
                role="button"
                tabIndex={0}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                  <span className="slot-type-badge">{slot.slot_type}</span>
                  <span className="text-muted" style={{ fontSize: '0.6875rem' }}>F{slot.floor}</span>
                </div>

                <div className="slot-number" style={{ margin: '0.35rem 0' }}>
                  {slot.number}
                </div>

                {slot.current_booking ? (
                  <div style={{ fontSize: '0.6875rem', fontWeight: 600, color: '#92400e' }}>
                    🚘 {slot.current_booking.vehicle_plate}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.6875rem', color: isOccupied ? '#92400e' : isOutOfService ? '#991b1b' : '#166534', fontWeight: 500 }}>
                    {slot.status}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      {/* Slot Details & Manual Physical Override Modal */}
      <Modal
        isOpen={selectedSlot !== null}
        title={`Slot Details: ${selectedSlot?.number}`}
        onClose={() => setSelectedSlot(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelectedSlot(null)}>
              Close
            </Button>
            {selectedSlot?.status === 'AVAILABLE' && (
              <Button
                variant="warning"
                loading={marking}
                onClick={() => handleMarkOccupancy('OCCUPIED')}
              >
                Mark Physically Occupied
              </Button>
            )}
            {selectedSlot?.status === 'OCCUPIED' && (
              <Button
                variant="success"
                loading={marking}
                onClick={() => handleMarkOccupancy('AVAILABLE')}
              >
                Mark Physically Free
              </Button>
            )}
          </>
        }
      >
        {selectedSlot && (
          <div>
            {markError && (
              <div className="error-state mb-4" role="alert">
                <div className="error-icon">⚠️</div>
                <div className="error-content">
                  <p className="error-message">{markError}</p>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginBottom: '1.25rem' }}>
              <div className="flex justify-between">
                <span className="text-muted">Bay Identifier</span>
                <span className="font-semibold">{selectedSlot.number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Floor</span>
                <span>Floor {selectedSlot.floor}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Category</span>
                <span className="badge badge-info">{selectedSlot.slot_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted">Physical Flag</span>
                <span className="font-semibold">{selectedSlot.status}</span>
              </div>
            </div>

            {selectedSlot.current_booking ? (
              <div style={{ background: '#fef3c7', border: '1px solid #fde68a', padding: '0.85rem', borderRadius: '6px' }}>
                <h4 style={{ fontSize: '0.9375rem', fontWeight: 600, color: '#92400e', marginBottom: '0.5rem' }}>
                  Current In-Progress Booking
                </h4>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                  <span>Pass Reference:</span>
                  <span className="font-mono font-semibold">{selectedSlot.current_booking.reference}</span>
                </div>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                  <span>Vehicle:</span>
                  <span className="font-mono font-semibold">{selectedSlot.current_booking.vehicle_plate}</span>
                </div>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                  <span>Customer:</span>
                  <span>{selectedSlot.current_booking.consumer_email}</span>
                </div>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                  <span>Check-in Entry:</span>
                  <span>{formatDateTime(selectedSlot.current_booking.actual_entry_at)}</span>
                </div>
                <div className="flex justify-between" style={{ fontSize: '0.8125rem' }}>
                  <span>Reserved Until:</span>
                  <span>{formatDateTime(selectedSlot.current_booking.end_time)}</span>
                </div>
              </div>
            ) : (
              <div style={{ background: '#f8fafc', padding: '0.75rem', borderRadius: '4px', border: '1px solid #e2e8f0' }}>
                <span className="text-muted" style={{ fontSize: '0.8125rem' }}>
                  No active in-progress booking session associated with this bay right now.
                </span>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

