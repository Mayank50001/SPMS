// Card container component
import React from 'react'

export interface CardProps {
  title?: React.ReactNode
  subtitle?: React.ReactNode
  action?: React.ReactNode
  children: React.ReactNode
  className?: string
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  action,
  children,
  className = '',
}) => {
  return (
    <div className={`card ${className}`}>
      {(title || action) && (
        <div className="card-header">
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {action && <div className="card-actions">{action}</div>}
        </div>
      )}
      <div className="card-body">{children}</div>
    </div>
  )
}

