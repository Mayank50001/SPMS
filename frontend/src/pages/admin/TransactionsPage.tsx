// Administrator Financial Transactions & Refunds Ledger Page (Phase 5 / D61 / D65)
import React, { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { usePaginated } from '../../hooks/usePaginated'
import { apiFetch } from '../../api/client'
import { ApiError, getFriendlyErrorMessage } from '../../api/errors'
import type { OperatorPaymentRow, ParkingLot, RefundRow, PaymentStatus } from '../../api/types'
import { Card } from '../../components/common/Card'
import { Button } from '../../components/common/Button'
import { Badge, PaymentStatusBadge } from '../../components/common/Badge'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
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

  // Facilities for filter
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
      <PageHeader
        eyebrow="Finance"
        title="Transactions &amp; ledger"
        subtitle="Platform-wide payment logs, methods and refund processing"
      />

      {/* Filter Bar */}
      <form onSubmit={handleFilterSubmit} className="filter-bar">
        <div style={{ minWidth: '160px' }}>
          <select
            className="form-control"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All payment statuses</option>
            <option value="SUCCEEDED">Succeeded</option>
            <option value="PENDING">Pending</option>
            <option value="FAILED">Failed</option>
          </select>
        </div>

        <div style={{ minWidth: '160px' }}>
          <select
            className="form-control"
            value={purposeFilter}
            onChange={(e) => setPurposeFilter(e.target.value)}
          >
            <option value="">All purposes</option>
            <option value="BOOKING">Booking charge</option>
            <option value="EXTENSION">Window extension</option>
          </select>
        </div>

        <div style={{ minWidth: '200px' }}>
          <select
            className="form-control"
            value={lotFilter}
            onChange={(e) => setLotFilter(e.target.value)}
          >
            <option value="">All facilities</option>
            {lots.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name} ({l.code})
              </option>
            ))}
          </select>
        </div>

        <Button type="submit" variant="primary">
          <Icon name="search" size={16} /> Filter ledger
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
            <Icon name="close" size={16} /> Clear
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
                    <th>Booking pass</th>
                    <th>Customer</th>
                    <th>Facility &amp; slot</th>
                    <th>Purpose / method</th>
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
                        <div className="font-mono text-muted" style={{ fontSize: '0.75rem' }}>
                          {tx.vehicle_plate}
                        </div>
                      </td>
                      <td>
                        <div>{tx.lot_name}</div>
                        <div className="text-muted" style={{ fontSize: '0.75rem' }}>
                          Slot {tx.slot_number}
                        </div>
                      </td>
                      <td>
                        <Badge variant="info">{tx.purpose}</Badge>
                        <div className="text-muted" style={{ fontSize: '0.75rem', marginTop: '0.25rem' }}>
                          {tx.method}
                        </div>
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
                          <Button variant="outline" size="sm" onClick={() => handleOpenRefund(tx)}>
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
        title={`Process ledger refund: Tx #${refundingPayment?.id}`}
        onClose={() => setRefundingPayment(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setRefundingPayment(null)}>
              {refundSuccess ? 'Close' : 'Cancel'}
            </Button>
            {!refundSuccess && (
              <Button variant="danger" loading={refunding} onClick={handleExecuteRefund}>
                Confirm full refund
              </Button>
            )}
          </>
        }
      >
        {refundingPayment && (
          <div>
            {refundSuccess ? (
              <div className="alert alert-success mb-0" role="status">
                <span className="alert-icon text-success">
                  <Icon name="check" size={18} />
                </span>
                <div className="alert-body">
                  <p className="alert-title">Refund issued successfully</p>
                  <p>
                    Refund ledger event #{refundSuccess.id} created for amount{' '}
                    {formatMoney(refundSuccess.amount)}. Status: {refundSuccess.status}.
                  </p>
                </div>
              </div>
            ) : (
              <div>
                <p style={{ marginBottom: '1rem' }}>
                  Are you sure you want to issue a refund for this captured transaction?
                </p>

                <div className="info-list">
                  <div className="info-row">
                    <span className="info-label">Customer</span>
                    <span className="info-value">{refundingPayment.consumer_email}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Booking reference</span>
                    <span className="info-value font-mono">{refundingPayment.booking_reference}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Refund amount</span>
                    <span className="info-value text-danger">
                      {formatMoney(refundingPayment.amount)}
                    </span>
                  </div>
                </div>

                <p className="muted-sm mt-3 mb-0">
                  Per Decision D61: refunds are executed as ledger event rows (Refund), never
                  mutating the original captured Payment entry.
                </p>

                {refundError && (
                  <div className="alert alert-danger mt-3 mb-0" role="alert">
                    <span className="alert-icon text-danger">
                      <Icon name="alert" size={18} />
                    </span>
                    <div className="alert-body">
                      <p>{refundError}</p>
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