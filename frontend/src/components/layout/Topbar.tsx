// Slim top bar: mobile menu toggle, portal context, IST clock, user menu.
import React, { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import type { UserRole } from '../../api/types'
import { RoleBadge } from '../common/Badge'
import { Icon } from '../common/Icon'

const PORTAL_LABEL: Record<UserRole, string> = {
  CONSUMER: 'Driver Portal',
  MANAGER: 'Operations Portal',
  ADMIN: 'Administration',
}

const PROFILE_PATH: Record<UserRole, string> = {
  CONSUMER: '/consumer/profile',
  MANAGER: '/manager/profile',
  ADMIN: '/admin/profile',
}

const initials = (name: string): string => {
  const source = name.trim() || '?'
  const parts = source.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return source.slice(0, 2).toUpperCase()
}

const formatClock = (): string =>
  new Intl.DateTimeFormat('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Kolkata',
  }).format(new Date())

export interface TopbarProps {
  onMenuClick: () => void
}

export const Topbar: React.FC<TopbarProps> = ({ onMenuClick }) => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [clock, setClock] = useState<string>(formatClock)
  const menuRef = useRef<HTMLDivElement>(null)

  // Keep the IST clock fresh (cheap, once every 30s).
  useEffect(() => {
    const id = window.setInterval(() => setClock(formatClock()), 30_000)
    return () => window.clearInterval(id)
  }, [])

  // Close the dropdown on an outside click.
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const handleLogout = async () => {
    setOpen(false)
    await logout()
    navigate('/login')
  }

  const portal = user ? PORTAL_LABEL[user.role] : 'SPMS'
  const profilePath = user ? PROFILE_PATH[user.role] : '/login'

  return (
    <header className="topbar">
      <button
        type="button"
        className="topbar-menu-btn"
        aria-label="Toggle navigation"
        onClick={onMenuClick}
      >
        <Icon name="menu" size={20} />
      </button>

      <div className="topbar-context">
        <span className="topbar-eyebrow">{portal}</span>
        <span className="topbar-title">Smart Parking Management System</span>
      </div>

      <div className="topbar-spacer" />

      <div className="topbar-clock" title="Asia/Kolkata (IST)">
        <Icon name="clock" size={15} />
        <span>{clock} IST</span>
      </div>

      {user ? (
        <div className="user-menu" ref={menuRef}>
          {user.role && <RoleBadge role={user.role} />}
          <button
            type="button"
            className="user-button"
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <span className="user-avatar">{initials(user.full_name || user.email)}</span>
            <span className="user-meta">
              <span className="user-name">{user.full_name || 'Account'}</span>
              <span className="user-email">{user.email}</span>
            </span>
            <Icon name="chevronDown" size={16} />
          </button>

          {open && (
            <div className="user-dropdown" role="menu">
              <div className="user-dropdown-header">
                <div className="user-name">{user.full_name || 'Account'}</div>
                <div className="user-email">{user.email}</div>
              </div>
              <Link
                to={profilePath}
                className="user-dropdown-item"
                role="menuitem"
                onClick={() => setOpen(false)}
              >
                <Icon name="user" size={16} />
                Profile
              </Link>
              <button
                type="button"
                className="user-dropdown-item danger"
                role="menuitem"
                onClick={handleLogout}
              >
                <Icon name="logout" size={16} />
                Sign Out
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="auth-links">
          <Link to="/login" className="btn btn-outline btn-sm">
            Sign In
          </Link>
          <Link to="/register" className="btn btn-primary btn-sm">
            Register
          </Link>
        </div>
      )}
    </header>
  )
}