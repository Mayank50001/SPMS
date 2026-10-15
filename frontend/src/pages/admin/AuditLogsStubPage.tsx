// Administrator Audit Logs Stub (Deferred / D82)
import React from 'react'
import { Card } from '../../components/common/Card'
import { StubBanner } from '../../components/common/StubBanner'

export const AuditLogsStubPage: React.FC = () => {
  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Platform Audit Logs</h1>
          <p className="page-subtitle">Security audit trail, permission modifications, and administrative events</p>
        </div>
      </div>

      <StubBanner
        featureName="Security & System Audit Logging"
        decisionRef="Deferred Feature"
        description="Comprehensive audit logging and the audit log API surface are deferred in the current backend freeze. Per PROJECT.md §11/§23 guardrails, the frontend does not fabricate mock events or query unverified paths."
      />

      <Card title="Audit Event Scope">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', fontSize: '0.875rem' }}>
          <p>
            When wired to an audit log backend service, this screen will capture:
          </p>
          <ul style={{ paddingLeft: '1.25rem', lineHeight: '1.6' }}>
            <li>Administrator user suspensions and privilege demotions (D24).</li>
            <li>Business policy threshold changes (D35 / D45 / D70).</li>
            <li>Tariff price overrides and parking bay out-of-service withdrawals.</li>
            <li>Manual financial refunds and settlement reconciliation ledger entries.</li>
          </ul>
          <pre className="stub-code mt-2">
            <code>// TODO: Backend endpoint required for administrative audit logs</code>
          </pre>
        </div>
      </Card>
    </div>
  )
}

