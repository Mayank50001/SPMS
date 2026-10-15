// Persistent sidebar — role-grouped navigation.
import React from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import type { UserRole } from '../../api/types'
import { Icon } from '../common/Icon'
import type { IconName } from '../common/Icon'

interface NavItem {
  to: string
  label: string
  icon: IconName
  end?: boolean
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const NAV: Record<UserRole, NavGroup[]> = {
  CONSUMER: [
    {
      label: 'Driver',
      items: [
        { to: '/consumer', label: 'Dashboard', icon: 'dashboard', end: true },
        { to: '/consumer/search', label: 'Find Parking', icon: 'search' },
        { to: '/consumer/bookings', label: 'My Bookings', icon: 'calendar' },
        { to: '/consumer/vehicles', label: 'Vehicles', icon: 'car' },
      ],
    },
    {
      label: 'Account',
      items: [{ to: '/consumer/profile', label: 'Profile', icon: 'user' }],
    },
  ],
  MANAGER: [
    {
      label: 'Operations',
      items: [
        { to: '/manager', label: 'Dashboard', icon: 'dashboard', end: true },
        { to: '/manager/lots', label: 'My Parking Lots', icon: 'building' },
        { to: '/manager/bookings', label: 'Bookings', icon: 'calendar' },
        { to: '/manager/walk-in', label: 'Walk-in', icon: 'plus' },
      ],
    },
    {
      label: 'Insights',
      items: [{ to: '/manager/reports', label: 'Reports', icon: 'chart' }],
    },
    {
      label: 'Account',
      items: [{ to: '/manager/profile', label: 'Profile', icon: 'user' }],
    },
  ],
  ADMIN: [
    {
      label: 'Overview',
      items: [{ to: '/admin', label: 'Dashboard', icon: 'dashboard', end: true }],
    },
    {
      label: 'People',
      items: [
        { to: '/admin/users', label: 'Users', icon: 'users' },
        { to: '/admin/managers', label: 'Managers', icon: 'user' },
      ],
    },
    {
      label: 'Platform',
      items: [
        { to: '/admin/lots', label: 'Parking Lots', icon: 'building' },
        { to: '/admin/rules', label: 'Business Rules', icon: 'sliders' },
        { to: '/admin/bookings', label: 'Bookings', icon: 'calendar' },
        { to: '/admin/transactions', label: 'Transactions', icon: 'wallet' },
      ],
    },
    {
      label: 'Insights',
      items: [
        { to: '/admin/reports', label: 'Reports', icon: 'chart' },
        { to: '/admin/audit-logs', label: 'Audit Logs', icon: 'shield' },
      ],
    },
    {
      label: 'Account',
      items: [{ to: '/admin/profile', label: 'Profile', icon: 'user' }],
    },
  ],
}

export interface SidebarProps {
  open: boolean
  onClose: () => void
}

export const Sidebar: React.FC<SidebarProps> = ({ open, onClose }) => {
  const { user } = useAuth()
  const groups = user ? NAV[user.role] : []

  return (
    <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Primary navigation">
      <div className="sidebar-brand">
        <span className="sidebar-logo">🅿️</span>
        <span className="sidebar-brand-text">
          <span className="sidebar-brand-name">SPMS</span>
          <span className="sidebar-brand-sub">Parking Platform</span>
        </span>
      </div>

      <nav className="sidebar-nav">
        {groups.map((group) => (
          <div className="sidebar-group" key={group.label}>
            <div className="sidebar-group-label">{group.label}</div>
            {group.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
                onClick={onClose}
              >
                <span className="sidebar-link-icon">
                  <Icon name={item.icon} size={18} />
                </span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">SPMS · Phase 9 · v1.0</div>
    </aside>
  )
}