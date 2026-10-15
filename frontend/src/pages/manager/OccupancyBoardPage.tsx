// Live Occupancy Board with WebSocket & HTTP polling fallback (Phase 6 / D71 / D72)
import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { apiFetch, getStoredAccessToken } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { OccupancyBoard, OccupancyBoardSlot, PhysicalSlotStatus } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { Modal } from '../../components/common/Modal'
import { StatTile } from '../../components/common/StatTile'
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
      <Link to={`/manager/lots/${lotId}`} className="link-back mb-3">
        <span aria-hidden="true">←</span> Back to facility
      </Link>

      <PageHeader
        eyebrow={
          <span className="badge-row">
            <Badge variant={wsConnected ? 'success' : 'warning'}>
              {wsConnected ? 'Live' : 'Polling'}
            </Badge>
            <span>Facility {board?.lot.code}</span>
          </span>
        }
        title={board?.lot.name || 'Parking facility'}
        subtitle="Live bay status and in-progress sessions"
        actions={
          <Button variant="outline" size="sm" onClick={fetchBoardHttp}>
            <Icon name="refresh" size={15} /> Sync board
          </Button>
        }
      />

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-4 mb-4">
        <StatTile
          label="Total bays"
          value={board?.summary.total ?? 0}
          icon="grid"
          tone="default"
          meta="Configured capacity"
        />
        <StatTile
          label="Available bays"
          value={board?.summary.available ?? 0}
          icon="check"
          tone="success"
          meta="Free for parking"
        />
        <StatTile
          label="Occupied bays"
          value={board?.summary.occupied ?? 0}
          icon="car"
          tone="warning"
          meta="Physically in use"
        />
        <StatTile
          label="Out of service"
          value={board?.summary.out_of_service ?? 0}
          icon="alert"
          tone="danger"
          meta="Maintenance / closed"
        />
      </div>

      {/* Bay Visual Grid */}
      <Card
        title="Parking bay layout"
        subtitle="Click any bay to view its in-progress reservation or override physical occupancy"
      >
        {board && board.slots.length > 0 && (
          <div className="legend mb-3">
            <span className="legend-item">
              <span className="legend-dot bay-available" /> Available
            </span>
            <span className="legend-item">
              <span className="legend-dot bay-occupied" /> Occupied
            </span>
            <span className="legend-item">
              <span className="legend-dot bay-out-of-service" /> Out of service
            </span>
          </div>
        )}

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
                onClick={() => {
                  setMarkError(null)
                  setSelectedSlot(slot)
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setMarkError(null)
                    setSelectedSlot(slot)
                  }
                }}
                role="button"
                tabIndex={0}
              >
                <div className="row-between" style={{ width: '100%' }}>
                  <span className="slot-type-badge">{slot.slot_type}</span>
                  <span className="text-subtle" style={{ fontSize: '0.6875rem' }}>
                    F{slot.floor}
                  </span>
                </div>

                <div className="slot-number" style={{ margin: '0.35rem 0' }}>
                  {slot.number}
                </div>

                {slot.current_booking ? (
                  <span className="plate" style={{ fontSize: '0.75rem' }}>
                    {slot.current_booking.vehicle_plate}
                  </span>
                ) : (
                  <span
                    className="text-muted"
                    style={{ fontSize: '0.6875rem', fontWeight: 600, textTransform: 'uppercase' }}
                  >
                    {slot.status.replace(/_/g, ' ')}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      </Card>

      {/* Slot Details & Manual Physical Override Modal */}
      <Modal
        isOpen={selectedSlot !== null}
        title={`Slot details: ${selectedSlot?.number}`}
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
                Mark physically occupied
              </Button>
            )}
            {selectedSlot?.status === 'OCCUPIED' && (
              <Button
                variant="success"
                loading={marking}
                onClick={() => handleMarkOccupancy('AVAILABLE')}
              >
                Mark physically free
              </Button>
            )}
          </>
        }
      >
        {selectedSlot && (
          <div>
            {markError && (
              <div className="alert alert-danger" role="alert">
                <span className="alert-icon text-danger">
                  <Icon name="alert" size={18} />
                </span>
                <div className="alert-body">
                  <p>{markError}</p>
                </div>
              </div>
            )}

            <div className="info-list">
              <div className="info-row">
                <span className="info-label">Bay identifier</span>
                <span className="info-value font-mono">{selectedSlot.number}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Floor</span>
                <span className="info-value">Floor {selectedSlot.floor}</span>
              </div>
              <div className="info-row">
                <span className="info-label">Category</span>
                <span className="info-value">
                  <Badge variant="info">{selectedSlot.slot_type}</Badge>
                </span>
              </div>
              <div className="info-row">
                <span className="info-label">Physical flag</span>
                <span className="info-value">{selectedSlot.status.replace(/_/g, ' ')}</span>
              </div>
            </div>

            {selectedSlot.current_booking ? (
              <div className="alert alert-warning mt-3 mb-0">
                <span className="alert-icon">
                  <Icon name="car" size={18} />
                </span>
                <div className="alert-body">
                  <p className="alert-title">Current in-progress booking</p>
                  <div className="row-between">
                    <span>Pass reference</span>
                    <span className="font-mono font-semibold">
                      {selectedSlot.current_booking.reference}
                    </span>
                  </div>
                  <div className="row-between">
                    <span>Vehicle</span>
                    <span className="font-mono font-semibold">
                      {selectedSlot.current_booking.vehicle_plate}
                    </span>
                  </div>
                  <div className="row-between">
                    <span>Customer</span>
                    <span>{selectedSlot.current_booking.consumer_email}</span>
                  </div>
                  <div className="row-between">
                    <span>Check-in entry</span>
                    <span>{formatDateTime(selectedSlot.current_booking.actual_entry_at)}</span>
                  </div>
                  <div className="row-between">
                    <span>Reserved until</span>
                    <span>{formatDateTime(selectedSlot.current_booking.end_time)}</span>
                  </div>
                </div>
              </div>
            ) : (
              <p className="text-muted mt-3 mb-0" style={{ fontSize: '0.875rem' }}>
                No active in-progress booking session is associated with this bay right now.
              </p>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}