// Visual status badges
import React from 'react'
import type { BookingStatus, PhysicalSlotStatus, PaymentStatus, UserRole } from '../../api/types'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral'
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = 'default' }) => {
  return <span className={`badge badge-${variant}`}>{children}</span>
}

export const BookingStatusBadge: React.FC<{ status: BookingStatus }> = ({ status }) => {
  switch (status) {
    case 'CONFIRMED':
      return <Badge variant="success">Confirmed</Badge>
    case 'IN_PROGRESS':
      return <Badge variant="info">In Progress</Badge>
    case 'COMPLETED':
      return <Badge variant="neutral">Completed</Badge>
    case 'PENDING_PAYMENT':
      return <Badge variant="warning">Pending Payment</Badge>
    case 'EXPIRED':
      return <Badge variant="neutral">Expired</Badge>
    case 'CANCELLED':
      return <Badge variant="danger">Cancelled</Badge>
    case 'TERMINATED':
      return <Badge variant="danger">Terminated</Badge>
    default:
      return <Badge>{status}</Badge>
  }
}

export const SlotStatusBadge: React.FC<{ status: PhysicalSlotStatus }> = ({ status }) => {
  switch (status) {
    case 'AVAILABLE':
      return <Badge variant="success">Available</Badge>
    case 'OCCUPIED':
      return <Badge variant="warning">Occupied</Badge>
    case 'OUT_OF_SERVICE':
      return <Badge variant="danger">Out of Service</Badge>
    default:
      return <Badge>{status}</Badge>
  }
}

export const PaymentStatusBadge: React.FC<{ status: PaymentStatus }> = ({ status }) => {
  switch (status) {
    case 'SUCCEEDED':
      return <Badge variant="success">Succeeded</Badge>
    case 'PENDING':
      return <Badge variant="warning">Pending</Badge>
    case 'FAILED':
      return <Badge variant="danger">Failed</Badge>
    default:
      return <Badge>{status}</Badge>
  }
}

export const RoleBadge: React.FC<{ role: UserRole }> = ({ role }) => {
  switch (role) {
    case 'ADMIN':
      return <Badge variant="danger">Administrator</Badge>
    case 'MANAGER':
      return <Badge variant="info">Parking Manager</Badge>
    case 'CONSUMER':
      return <Badge variant="success">Consumer</Badge>
    default:
      return <Badge>{role}</Badge>
  }
}

