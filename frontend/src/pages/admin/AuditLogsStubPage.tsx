// Administrator Audit Logs Stub (Deferred / D82)
import React from 'react'
import { Card } from '../../components/common/Card'
import { Icon } from '../../components/common/Icon'
import { PageHeader } from '../../components/common/PageHeader'
import { StubBanner } from '../../components/common/StubBanner'

export const AuditLogsStubPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        eyebrow="Deferred"
        title="Platform audit logs"
        subtitle="Security audit trail, permission modifications and administrative events"
      />

      <StubBanner
        featureName="Security & System Audit Logging"
        decisionRef="Deferred Feature"
        description="Comprehensive audit logging and the audit log API surface are deferred in the current backend freeze. Per PROJECT.md §11/§23 guardrails, the frontend does not fabricate mock events or query unverified paths."
      />

      <Card title="Audit event scope" subtitle="What this trail will capture once wired">
        <p className="muted-sm mb-0">
          When connected to an audit log backend service, this screen will record:
        </p>

        <div className="check-list mt-3">
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Administrator user suspensions and privilege demotions (D24).</span>
          </div>
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Business policy threshold changes (D35 / D45 / D70).</span>
          </div>
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Tariff price overrides and parking bay out-of-service withdrawals.</span>
          </div>
          <div className="check-list-item">
            <Icon name="check" size={16} />
            <span>Manual financial refunds and settlement reconciliation ledger entries.</span>
          </div>
        </div>

        <pre className="stub-code mt-4">
          <code>// TODO: Backend endpoint required for administrative audit logs</code>
        </pre>
      </Card>
    </div>
  )
}