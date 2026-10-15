// Stub banner for unavailable backend features per D82
import React from 'react'

export interface StubBannerProps {
  featureName: string
  decisionRef?: string
  description?: string
}

export const StubBanner: React.FC<StubBannerProps> = ({
  featureName,
  decisionRef = 'D63 / Deferred',
  description = 'This capability is deferred in the current backend API freeze. In compliance with the project specification (PROJECT.md §11/§23), the client does not fake routes or fabricate mock data.',
}) => {
  return (
    <div className="stub-banner">
      <div className="stub-icon">🚧</div>
      <div className="stub-content">
        <div className="stub-header">
          <h4 className="stub-title">{featureName} — Feature Deferred</h4>
          <span className="stub-tag">{decisionRef}</span>
        </div>
        <p className="stub-description">{description}</p>
        <pre className="stub-code"><code>// TODO: Backend endpoint required</code></pre>
      </div>
    </div>
  )
}

