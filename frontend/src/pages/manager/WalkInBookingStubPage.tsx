// Manager Walk-in Booking Stub (D63 / D82)
import React from 'react'
import { Card } from '../../components/common/Card'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { StubBanner } from '../../components/common/StubBanner'

export const WalkInBookingStubPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        eyebrow="Deferred"
        title="Walk-in booking &amp; cash entry"
        subtitle="Immediate drive-up customer registration and cash payment intake"
      />

      <StubBanner
        featureName="Walk-in Booking & Cash Settlement"
        decisionRef="Decision D63"
        description="Walk-in booking creation and manager cash payment workflows are deferred in the current backend API freeze. Under project specification guardrails (PROJECT.md §11/§23), offline database writes or unverified routes are strictly forbidden."
      />

      <Card title="Architecture status" subtitle="Why this screen is read-only for now">
        <div className="stack-sm">
          <p className="muted-sm mb-0">
            When walk-in booking is implemented in a future phase, it will let Parking Managers
            immediately allocate an available slot to an unannounced drive-up vehicle and record
            cash collection at the gate.
          </p>
          <p className="muted-sm mb-0">
            The database model already supports nullable user references (D8), but the dedicated API
            write route is scheduled for a future backend milestone.
          </p>
        </div>

        <div className="check-list mt-4">
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Allocate an available bay to a drive-up vehicle</span>
          </div>
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Record cash payment intake at the gate</span>
          </div>
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Issue a gate pass without a consumer account</span>
          </div>
        </div>

        <pre className="stub-code mt-4">
          <code>// TODO: Backend endpoint required for walk-in booking and cash payment (D63)</code>
        </pre>
      </Card>
    </div>
  )
}