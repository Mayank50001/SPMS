// Error state component
import React from 'react'
import { getFriendlyErrorMessage } from '../../api/errors'
import { Button } from './Button'

export interface ErrorStateProps {
  error: unknown
  title?: string
  onRetry?: () => void
}

export const ErrorState: React.FC<ErrorStateProps> = ({
  error,
  title = 'Something went wrong',
  onRetry,
}) => {
  const message = getFriendlyErrorMessage(error)

  return (
    <div className="error-state" role="alert">
      <div className="error-icon">⚠️</div>
      <div className="error-content">
        <h4 className="error-title">{title}</h4>
        <p className="error-message">{message}</p>
        {onRetry && (
          <Button variant="secondary" size="sm" onClick={onRetry} className="mt-2">
            Try again
          </Button>
        )}
      </div>
    </div>
  )
}

