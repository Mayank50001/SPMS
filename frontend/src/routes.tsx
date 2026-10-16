// Application Route Definitions
import React from 'react'
import { Routes, Route } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { RequireAuth, RequireRole } from './auth/guards'

// Auth Pages
import { LoginPage } from './pages/auth/LoginPage'
import { RegisterPage } from './pages/auth/RegisterPage'
import { ProfilePage } from './pages/common/ProfilePage'
import { NotFoundPage } from './pages/NotFoundPage'
import { LandingPage } from './pages/LandingPage'

// Consumer Pages
import { ConsumerDashboardPage } from './pages/consumer/ConsumerDashboardPage'
import { ParkingSearchPage } from './pages/consumer/ParkingSearchPage'
import { LotDetailsPage } from './pages/consumer/LotDetailsPage'
import { SlotSelectionPage } from './pages/consumer/SlotSelectionPage'
import { PaymentPage } from './pages/consumer/PaymentPage'
import { BookingConfirmationPage } from './pages/consumer/BookingConfirmationPage'
import { MyBookingsPage } from './pages/consumer/MyBookingsPage'
import { BookingDetailsPage } from './pages/consumer/BookingDetailsPage'
import { VehiclesPage } from './pages/consumer/VehiclesPage'

// Manager Pages
import { ManagerDashboardPage } from './pages/manager/ManagerDashboardPage'
import { MyLotsPage } from './pages/manager/MyLotsPage'
import { ManagerLotDetailsPage } from './pages/manager/ManagerLotDetailsPage'
import { SlotManagementPage } from './pages/manager/SlotManagementPage'
import { TariffManagementPage } from './pages/manager/TariffManagementPage'
import { OccupancyBoardPage } from './pages/manager/OccupancyBoardPage'
import { ManagerBookingsPage } from './pages/manager/ManagerBookingsPage'
import { ManagerReportsPage } from './pages/manager/ManagerReportsPage'
import { WalkInBookingStubPage } from './pages/manager/WalkInBookingStubPage'

// Admin Pages
import { AdminDashboardPage } from './pages/admin/AdminDashboardPage'
import { UsersPage } from './pages/admin/UsersPage'
import { ManagersPage } from './pages/admin/ManagersPage'
import { AdminLotsPage } from './pages/admin/AdminLotsPage'
import { BusinessRulesPage } from './pages/admin/BusinessRulesPage'
import { TransactionsPage } from './pages/admin/TransactionsPage'
import { AdminReportsPage } from './pages/admin/AdminReportsPage'
import { AuditLogsStubPage } from './pages/admin/AuditLogsStubPage'

export const AppRoutes: React.FC = () => {
  return (
    <Routes>
      {/* Public landing page (signed-in users are redirected to their portal) */}
      <Route path="/" element={<LandingPage />} />

      {/* Public Auth Routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Main Authenticated Layout */}
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        {/* Consumer Portal Routes */}
        <Route
          path="/consumer"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <ConsumerDashboardPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/search"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <ParkingSearchPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/lots/:id"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <LotDetailsPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/lots/:id/slots"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <SlotSelectionPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/payment/:bookingId"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <PaymentPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/confirmation/:bookingId"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <BookingConfirmationPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/bookings"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <MyBookingsPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/bookings/:id"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <BookingDetailsPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/vehicles"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <VehiclesPage />
            </RequireRole>
          }
        />
        <Route
          path="/consumer/profile"
          element={
            <RequireRole roles={['CONSUMER', 'MANAGER', 'ADMIN']}>
              <ProfilePage />
            </RequireRole>
          }
        />

        {/* Manager Portal Routes */}
        <Route
          path="/manager"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <ManagerDashboardPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/lots"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <MyLotsPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/lots/:lotId"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <ManagerLotDetailsPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/lots/:lotId/slots"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <SlotManagementPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/lots/:lotId/tariffs"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <TariffManagementPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/lots/:lotId/occupancy"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <OccupancyBoardPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/bookings"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <ManagerBookingsPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/reports"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <ManagerReportsPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/walk-in"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <WalkInBookingStubPage />
            </RequireRole>
          }
        />
        <Route
          path="/manager/profile"
          element={
            <RequireRole roles={['MANAGER', 'ADMIN']}>
              <ProfilePage />
            </RequireRole>
          }
        />

        {/* Admin Portal Routes */}
        <Route
          path="/admin"
          element={
            <RequireRole roles={['ADMIN']}>
              <AdminDashboardPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/users"
          element={
            <RequireRole roles={['ADMIN']}>
              <UsersPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/managers"
          element={
            <RequireRole roles={['ADMIN']}>
              <ManagersPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/lots"
          element={
            <RequireRole roles={['ADMIN']}>
              <AdminLotsPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/rules"
          element={
            <RequireRole roles={['ADMIN']}>
              <BusinessRulesPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/bookings"
          element={
            <RequireRole roles={['ADMIN']}>
              <ManagerBookingsPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/transactions"
          element={
            <RequireRole roles={['ADMIN']}>
              <TransactionsPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/reports"
          element={
            <RequireRole roles={['ADMIN']}>
              <AdminReportsPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/audit-logs"
          element={
            <RequireRole roles={['ADMIN']}>
              <AuditLogsStubPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/profile"
          element={
            <RequireRole roles={['ADMIN']}>
              <ProfilePage />
            </RequireRole>
          }
        />

        {/* 404 Catch-all */}
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

