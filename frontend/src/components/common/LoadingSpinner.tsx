// Loading indicators
import React from 'react'

export const LoadingSpinner: React.FC<{
  size?: 'sm' | 'md' | 'lg'
  message?: string
}> = ({ size = 'md', message }) => {
  return (
    <div className={`loading-container loading-${size}`}>
      <div className={`spinner spinner-${size}`} />
      {message && <p className="loading-message">{message}</p>}
    </div>
  )
}

