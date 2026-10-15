// KPI tile with optional icon and tone, used across all three dashboards.
import React from 'react'
import { Icon } from './Icon'
import type { IconName } from './Icon'

export type StatTone = 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info'

export interface StatTileProps {
  label: string
  value: React.ReactNode
  icon?: IconName
  tone?: StatTone
  meta?: React.ReactNode
}

export const StatTile: React.FC<StatTileProps> = ({
  label,
  value,
  icon,
  tone = 'default',
  meta,
}) => {
  return (
    <div className={`stat-card stat-card-${tone}`}>
      <div className="stat-head">
        <span className="stat-label">{label}</span>
        {icon && (
          <span className="stat-icon">
            <Icon name={icon} size={18} />
          </span>
        )}
      </div>
      <div className="stat-value">{value}</div>
      {meta && <div className="stat-meta">{meta}</div>}
    </div>
  )
}