// Empty state component
import React from 'react'

export interface EmptyStateProps {
  title?: string
  message: string
  action?: React.ReactNode
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  title = 'No items found',
  message,
  action,
}) => {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">📂</div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-message">{message}</p>
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  )
}

