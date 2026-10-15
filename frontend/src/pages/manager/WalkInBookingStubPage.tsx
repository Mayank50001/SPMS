// Manager Walk-in Booking Stub (D63 / D82)
import React from 'react'
import { Card } from '../../components/common/Card'
import { StubBanner } from '../../components/common/StubBanner'

export const WalkInBookingStubPage: React.FC = () => {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Walk-in Booking & Cash Entry</h1>
          <p className="page-subtitle">Immediate drive-up customer registration and cash payment intake</p>
        </div>
      </div>

      <StubBanner
        featureName="Walk-in Booking & Cash Settlement"
        decisionRef="Decision D63"
        description="Walk-in booking creation and manager cash payment workflows are deferred in the current backend API freeze. Under project specification guardrails (PROJECT.md §11/§23), offline database writes or unverified routes are strictly forbidden."
      />

      <Card title="Architecture Status">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
          <p>
            When walk-in booking is implemented in a future phase, it will allow Parking Managers to immediately allocate an available slot to an unannounced drive-up vehicle and record cash collection at gate.
          </p>
          <p className="text-muted">
            The database model already supports nullable user references (D8), but the dedicated API write route is scheduled for a future backend milestone.
          </p>
          <pre className="stub-code mt-2">
            <code>// TODO: Backend endpoint required for walk-in booking and cash payment (D63)</code>
          </pre>
        </div>
      </Card>
    </div>
  )
}

