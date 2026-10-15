// Pagination component driving ?page=N
import React from 'react'
import { Button } from './Button'

export interface PaginationProps {
  currentPage: number
  totalPages: number
  totalItems: number
  pageSize: number
  onPageChange: (page: number) => void
  loading?: boolean
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  onPageChange,
  loading = false,
}) => {
  if (totalItems <= pageSize && totalPages <= 1) {
    return null
  }

  const start = (currentPage - 1) * pageSize + 1
  const end = Math.min(currentPage * pageSize, totalItems)

  return (
    <div className="pagination-bar">
      <div className="pagination-info">
        Showing <strong>{start}</strong> to <strong>{end}</strong> of <strong>{totalItems}</strong> entries
      </div>
      <div className="pagination-controls">
        <Button
          variant="outline"
          size="sm"
          disabled={currentPage <= 1 || loading}
          onClick={() => onPageChange(currentPage - 1)}
        >
          Previous
        </Button>
        <span className="pagination-pages">
          Page {currentPage} of {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={currentPage >= totalPages || loading}
          onClick={() => onPageChange(currentPage + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

