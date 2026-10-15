// App shell: sidebar + topbar + content + footer.
import React, { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export const AppLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const location = useLocation()

  // Auto-close the mobile drawer on navigation.
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  return (
    <div className="app-shell">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <div className="shell-main">
        <Topbar onMenuClick={() => setSidebarOpen((v) => !v)} />

        <main className="app-content">
          <Outlet />
        </main>

        <footer className="app-footer">
          <span>© 2026 Smart Parking Management System (SPMS)</span>
          <span>Times shown in Asia/Kolkata (IST)</span>
        </footer>
      </div>
    </div>
  )
}