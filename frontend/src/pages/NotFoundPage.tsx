// 404 Not Found Page
import React from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../components/common/Card'

export const NotFoundPage: React.FC = () => {
  return (
    <div style={{ maxWidth: '480px', margin: '4rem auto' }}>
      <Card className="text-center">
        <div style={{ fontSize: '3rem', margin: '1rem 0' }}>🔍</div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>
          Page Not Found
        </h1>
        <p className="text-muted mb-4" style={{ fontSize: '0.875rem' }}>
          The requested page or resource could not be found.
        </p>
        <Link to="/" className="btn btn-primary">
          Back to Home
        </Link>
      </Card>
    </div>
  )
}

