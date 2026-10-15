// Administrator Financial Transactions & Refunds Ledger Page (Phase 5 / D61 / D65)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { OperatorPaymentRow, ParkingLot, RefundRow, PaymentStatus } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { PaymentStatusBadge } from '../../components/common/Badge'
import { Modal } from '../../components/common/Modal'
import { Pagination } from '../../components/common/Pagination'
import { LoadingSpinner } from '../../components/common/LoadingSpinner'
import { EmptyState } from '../../components/common/EmptyState'
import { formatMoney, formatDateTime } from '../../lib/format'

export const TransactionsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()

  const statusParam = searchParams.get('status') || ''
  const purposeParam = searchParams.get('purpose') || ''
  const lotParam = searchParams.get('lot') || ''

  const [statusFilter, setStatusFilter] = useState(statusParam)
  const [purposeFilter, setPurposeFilter] = useState(purposeParam)
  const [lotFilter, setLotFilter] = useState(lotParam)

  // Assigned / all facilities for filter
  const { results: lots } = usePaginated<ParkingLot>('/parking-lots/', { pageSize: 100 })

  // Payments transactions list
  const {
    results: transactions,
    count,
    page,
    pageSize,
    totalPages,
    loading,
    setPage,
    refetch,
  } = usePaginated<OperatorPaymentRow>('/payments/', {
    params: {
      status: statusParam || undefined,
      purpose: purposeParam || undefined,
      lot: lotParam || undefined,
      ordering: '-created_at',
    },
  })

  // Refund Modal State
  const [refundingPayment, setRefundingPayment] = useState<OperatorPaymentRow | null>(null)
  const [refunding, setRefunding] = useState(false)
  const [refundError, setRefundError] = useState<string | null>(null)
  const [refundSuccess, setRefundSuccess] = useState<RefundRow | null>(null)

  const handleFilterSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const sp = new URLSearchParams()
    if (statusFilter) sp.set('status', statusFilter)
    if (purposeFilter) sp.set('purpose', purposeFilter)
    if (lotFilter) sp.set('lot', lotFilter)
    setSearchParams(sp)
  }

  const handleOpenRefund = (tx: OperatorPaymentRow) => {
    setRefundingPayment(tx)
    setRefundError(null)
    setRefundSuccess(null)
  }

  const handleExecuteRefund = async () => {
    if (!refundingPayment) return
    setRefunding(true)
    setRefundError(null)

    try {
      const refund = await apiFetch<RefundRow>(`/payments/${refundingPayment.id}/refund/`, {
        method: 'POST',
      })
      setRefundSuccess(refund)
      refetch()
    } catch (err) {
      if (err instanceof ApiError) {
        setRefundError(getFriendlyErrorMessage(err))
      } else {
        setRefundError('Failed to execute refund.')
      }
    } finally {
      setRefunding(false)
    }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Financial Transactions & Ledger</h1>
          <p className="page-subtitle">Platform-wide payment logs, methods, and refund processing</p>
        </div>
      </div>

      {/* Filter Bar */}
      <form onSubmit={handleFilterSubmit} className="filter-bar">
        <div style={{ minWidth: '150px' }}>
          <select
            className="form-control"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All Payment Statuses</option>
            <option value="SUCCEEDED">Succeeded</option>
            <option value="PENDING">Pending</option>
            <option value="FAILED">Failed</option>
          </select>
        </div>

        <div style={{ minWidth: '150px' }}>
          <select
            className="form-control"
            value={purposeFilter}
            onChange={(e) => setPurposeFilter(e.target.value)}
          >
            <option value="">All Purposes</option>
            <option value="BOOKING">Booking Charge</option>
            <option value="EXTENSION">Window Extension</option>
          </select>
        </div>

        <div style={{ minWidth: '180px' }}>
          <select
            className="form-control"
            value={lotFilter}
            onChange={(e) => setLotFilter(e.target.value)}
          >
            <option value="">All Facilities</option>
            {lots.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.code})
              </option>
            ))}
          </select>
        </div>

        <Button type="submit" variant="primary">
          Filter Ledger
        </Button>

        {(statusParam || purposeParam || lotParam) && (
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setStatusFilter('')
              setPurposeFilter('')
              setLotFilter('')
              setSearchParams({})
            }}
          >
            Clear
          </Button>
        )}
      </form>

      <Card>
        {loading ? (
          <LoadingSpinner message="Querying transaction records..." />
        ) : transactions.length === 0 ? (
          <EmptyState
            title="No transactions found"
            message="No payment transactions match the selected filters."
          />
        ) : (
          <>
            <div className="table-wrapper">
              <table className="table">
                <thead>
                  <tr>
                    <th>Tx ID</th>
                    <th>Booking Pass</th>
                    <th>Customer</th>
                    <th>Facility & Slot</th>
                    <th>Purpose / Method</th>
                    <th>Amount</th>
                    <th>Refunded</th>
                    <th>Status</th>
                    <th>Timestamp</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.id}>
                      <td className="font-mono font-semibold">#{tx.id}</td>
                      <td className="font-mono font-semibold">{tx.booking_reference}</td>
                      <td>
                        <div style={{ fontSize: '0.8125rem' }}>{tx.consumer_email}</div>
                        <div className="font-mono text-muted" style={{ fontSize: '0.75rem' }}>{tx.vehicle_plate}</div>
                      </td>
                      <td>
                        <div>{tx.lot_name}</div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>Slot {tx.slot_number}</div>
                      </td>
                      <td>
                        <span className="badge badge-info">{tx.purpose}</span>
                        <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: '0.2rem' }}>{tx.method}</div>
                      </td>
                      <td className="font-semibold" style={{ fontSize: '1rem' }}>
                        {formatMoney(tx.amount)}
                      </td>
                      <td>
                        {Number(tx.refunded_amount) > 0 ? (
                          <span className="text-danger font-semibold">
                            {formatMoney(tx.refunded_amount)}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td>
                        <PaymentStatusBadge status={tx.status as PaymentStatus} />
                      </td>
                      <td style={{ fontSize: '0.8125rem' }}>
                        {formatDateTime(tx.paid_at || tx.created_at)}
                      </td>
                      <td>
                        {tx.status === 'SUCCEEDED' && Number(tx.refunded_amount) < Number(tx.amount) ? (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenRefund(tx)}
                          >
                            Refund
                          </Button>
                        ) : (
                          <span className="text-muted" style={{ fontSize: '0.75rem' }}>
                            Settled
                          </span>
                        )}
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

      {/* Process Refund Modal */}
      <Modal
        isOpen={refundingPayment !== null}
        title={`Process Ledger Refund: Tx #${refundingPayment?.id}`}
        onClose={() => setRefundingPayment(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRefundingPayment(null)}>
              Cancel
            </Button>
            {!refundSuccess && (
              <Button variant="danger" loading={refunding} onClick={handleExecuteRefund}>
                Confirm Full Refund
              </Button>
            )}
          </>
        }
      >
        {refundingPayment && (
          <div>
            {refundSuccess ? (
              <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', padding: '1rem', borderRadius: '6px', color: '#16a34a' }}>
                <h4 style={{ fontWeight: 600, marginBottom: '0.25rem' }}>✓ Refund Issued Successfully</h4>
                <p style={{ fontSize: '0.8125rem' }}>
                  Refund ledger event #{refundSuccess.id} created for amount {formatMoney(refundSuccess.amount)}. Status: {refundSuccess.status}.
                </p>
              </div>
            ) : (
              <div>
                <p style={{ marginBottom: '1rem' }}>
                  Are you sure you want to issue a refund for this captured transaction?
                </p>

                <div style={{ background: '#f8fafc', padding: '0.75rem', borderRadius: '4px', border: '1px solid #e2e8f0', marginBottom: '1rem' }}>
                  <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                    <span>Customer:</span>
                    <span>{refundingPayment.consumer_email}</span>
                  </div>
                  <div className="flex justify-between" style={{ fontSize: '0.8125rem', marginBottom: '0.25rem' }}>
                    <span>Booking Reference:</span>
                    <span className="font-mono">{refundingPayment.booking_reference}</span>
                  </div>
                  <div className="flex justify-between" style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
                    <span>Refund Amount:</span>
                    <span style={{ color: 'var(--danger)' }}>{formatMoney(refundingPayment.amount)}</span>
                  </div>
                </div>

                <p className="text-muted" style={{ fontSize: '0.8125rem' }}>
                  Per Decision D61: Refunds are executed as ledger event rows (`Refund`), never mutating the original captured Payment entry.
                </p>

                {refundError && (
                  <div className="error-state mt-3" role="alert">
                    <div className="error-icon">⚠️</div>
                    <div className="error-content">
                      <p className="error-message">{refundError}</p>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

