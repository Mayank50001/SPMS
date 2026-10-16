// Shared split-screen shell for the public auth pages (login / register).
// Left: brand panel. Right: the form card. Purely presentational.
import React from 'react'
import { Link } from 'react-router-dom'
import { Icon } from '../common/Icon'

export interface AuthPoint {
  icon: React.ComponentProps<typeof Icon>['name']
  title: string
  text: string
}

interface AuthShellProps {
  title: string
  subtitle: string
  asideTitle: string
  asideLead: string
  points: AuthPoint[]
  children: React.ReactNode
  footer: React.ReactNode
}

export const AuthShell: React.FC<AuthShellProps> = ({
  title,
  subtitle,
  asideTitle,
  asideLead,
  points,
  children,
  footer,
}) => {
  return (
    <div className="auth-shell">
      <aside className="auth-aside">
        <Link to="/" className="auth-aside-brand">
          <span className="landing-brand-mark">
            <Icon name="car" size={20} />
          </span>
          <span className="auth-aside-brand-text">
            <strong>SPMS</strong>
            <span>Smart Parking</span>
          </span>
        </Link>

        <div className="auth-aside-body">
          <h2 className="auth-aside-title">{asideTitle}</h2>
          <p className="auth-aside-lead">{asideLead}</p>

          <div className="auth-aside-points">
            {points.map((p) => (
              <div className="auth-aside-point" key={p.title}>
                <span className="auth-point-icon">
                  <Icon name={p.icon} size={15} />
                </span>
                <div>
                  <strong>{p.title}</strong>
                  <small>{p.text}</small>
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="auth-aside-foot">
          © {new Date().getFullYear()} SPMS · Smart Parking Management System
        </p>
      </aside>

      <main className="auth-main">
        <div className="auth-card">
          <Link to="/" className="link-back auth-back">
            <span aria-hidden="true">←</span> Back to home
          </Link>

          <div className="auth-header">
            <span className="auth-logo">
              <Icon name="car" size={22} />
            </span>
            <h1 className="auth-title">{title}</h1>
            <p className="auth-subtitle">{subtitle}</p>
          </div>

          {children}

          <div className="auth-footer">{footer}</div>
        </div>
      </main>
    </div>
  )
}