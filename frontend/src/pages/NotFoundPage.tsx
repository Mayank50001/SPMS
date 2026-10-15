// 404 Not Found Page
import React from 'react'
import { Link } from 'react-router-dom'
import { Card } from '../components/common/Card'
import { Icon } from '../components/common/Icon'

export const NotFoundPage: React.FC = () => {
  return (
    <div className="notfound-wrap">
      <Card className="text-center">
        <div className="icon-mark">
          <Icon name="search" size={32} />
        </div>
        <h1 className="page-title">Page not found</h1>
        <p className="muted-sm mb-4">
          The page or resource you're looking for doesn't exist or has moved.
        </p>
        <div className="toolbar" style={{ justifyContent: 'center' }}>
          <Link to="/" className="btn btn-primary btn-md">
            <Icon name="arrowRight" size={16} /> Back to home
          </Link>
        </div>
      </Card>
    </div>
  )
}