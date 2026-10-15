// AppLayout shell
import React from 'react'
import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'

export const AppLayout: React.FC = () => {
  return (
    <div className="app-shell">
      <Navbar />
      <main className="main-content">
        <div className="container">
          <Outlet />
        </div>
      </main>
      <footer className="footer">
        <div className="container footer-content">
          <p>© 2026 Smart Parking Management System (SPMS). Built for reliability.</p>
          <p className="footer-meta">Phase 9 Integration · Active Timezone: Asia/Kolkata (IST)</p>
        </div>
      </footer>
    </div>
  )
}

