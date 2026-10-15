// Navbar with role-specific navigation
import React from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../auth/useAuth'
import { RoleBadge } from '../common/Badge'
import { Button } from '../common/Button'

export const Navbar: React.FC = () => {
  const { user, logout, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <header className="navbar">
      <div className="navbar-container">
        <div className="navbar-brand">
          <Link to="/" className="brand-link">
            <span className="brand-logo">🅿️</span>
            <span className="brand-name">SPMS</span>
          </Link>
          {user && <RoleBadge role={user.role} />}
        </div>

        <nav className="navbar-nav">
          {isAuthenticated && user?.role === 'CONSUMER' && (
            <>
              <NavLink to="/consumer" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Dashboard
              </NavLink>
              <NavLink to="/consumer/search" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Find Parking
              </NavLink>
              <NavLink to="/consumer/bookings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                My Bookings
              </NavLink>
              <NavLink to="/consumer/vehicles" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Vehicles
              </NavLink>
              <NavLink to="/consumer/profile" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Profile
              </NavLink>
            </>
          )}

          {isAuthenticated && user?.role === 'MANAGER' && (
            <>
              <NavLink to="/manager" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Dashboard
              </NavLink>
              <NavLink to="/manager/lots" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                My Lots
              </NavLink>
              <NavLink to="/manager/bookings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Bookings
              </NavLink>
              <NavLink to="/manager/reports" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Reports
              </NavLink>
              <NavLink to="/manager/walk-in" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Walk-in
              </NavLink>
              <NavLink to="/manager/profile" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Profile
              </NavLink>
            </>
          )}

          {isAuthenticated && user?.role === 'ADMIN' && (
            <>
              <NavLink to="/admin" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Dashboard
              </NavLink>
              <NavLink to="/admin/users" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Users
              </NavLink>
              <NavLink to="/admin/managers" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Managers
              </NavLink>
              <NavLink to="/admin/lots" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Parking Lots
              </NavLink>
              <NavLink to="/admin/rules" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Business Rules
              </NavLink>
              <NavLink to="/admin/bookings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Bookings
              </NavLink>
              <NavLink to="/admin/transactions" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Transactions
              </NavLink>
              <NavLink to="/admin/reports" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Reports
              </NavLink>
              <NavLink to="/admin/audit-logs" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
                Audit Logs
              </NavLink>
            </>
          )}
        </nav>

        <div className="navbar-user">
          {isAuthenticated && user ? (
            <div className="user-menu">
              <span className="user-email" title={user.email}>
                {user.full_name || user.email}
              </span>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                Sign Out
              </Button>
            </div>
          ) : (
            <div className="auth-links">
              <Link to="/login" className="btn btn-outline btn-sm">
                Sign In
              </Link>
              <Link to="/register" className="btn btn-primary btn-sm ml-2">
                Register
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

