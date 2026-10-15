// Accessible Modal Dialog
import React, { useEffect } from 'react'
import { Button } from './Button'

export interface ModalProps {
  isOpen: boolean
  title: string
  children: React.ReactNode
  onClose: () => void
  footer?: React.ReactNode
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  title,
  children,
  onClose,
  footer,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true">
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3 className="modal-title">{title}</h3>
          <Button variant="subtle" size="sm" onClick={onClose} aria-label="Close modal">
            ✕
          </Button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

