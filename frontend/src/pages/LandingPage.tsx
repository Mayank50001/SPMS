// Public landing page (marketing) — shown to signed-out visitors at "/".
// Signed-in users are bounced straight to their role dashboard so this never
// gets in the way of the app itself.
import React from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'
import { Icon } from '../components/common/Icon'

const FEATURES: { icon: React.ComponentProps<typeof Icon>['name']; title: string; body: string }[] = [
  {
    icon: 'search',
    title: 'Live bay availability',
    body: 'Search by city or facility and see which bays are free right now — no guessing, no circling the block.',
  },
  {
    icon: 'calendar',
    title: 'Reserve in seconds',
    body: 'Pick a slot, choose your time window and lock it in. Slots are held while you complete payment.',
  },
  {
    icon: 'wallet',
    title: 'Cashless checkout',
    body: 'Pay securely online with a receipted transaction. No cash, no queueing at the exit barrier.',
  },
  {
    icon: 'ticket',
    title: 'Digital gate pass',
    body: 'Your booking reference doubles as the pass — show it at the gate and park.',
  },
  {
    icon: 'clock',
    title: 'Extend & overstay handling',
    body: 'Running late? Extend your window from your phone. Overstay charges are calculated fairly and transparently.',
  },
  {
    icon: 'chart',
    title: 'Operator analytics',
    body: 'Managers and admins get occupancy, revenue and booking reports across every facility.',
  },
]

const STEPS: { title: string; body: string }[] = [
  {
    title: 'Find your spot',
    body: 'Browse nearby facilities and compare live availability, tariffs and distance.',
  },
  {
    title: 'Reserve & pay',
    body: 'Choose your slot and window, then pay securely online. Your bay is held while you check out.',
  },
  {
    title: 'Park with your pass',
    body: 'Head in with your booking reference. Extend from the app if your plans change.',
  },
]

const ROLES: {
  icon: React.ComponentProps<typeof Icon>['name']
  tone: string
  title: string
  body: string
  points: string[]
}[] = [
  {
    icon: 'car',
    tone: '',
    title: 'For drivers',
    body: 'Everything you need to park without the hassle.',
    points: ['Search live availability', 'Reserve and pay online', 'Manage vehicles & bookings'],
  },
  {
    icon: 'building',
    tone: 'info',
    title: 'For managers',
    body: 'Run your facilities with real-time visibility.',
    points: ['Lots, slots & tariffs', 'Occupancy board', 'Bookings & reports'],
  },
  {
    icon: 'shield',
    tone: 'success',
    title: 'For admins',
    body: 'Govern the whole platform from one place.',
    points: ['Users & managers', 'Platform business rules', 'Transactions & analytics'],
  },
]

export const LandingPage: React.FC = () => {
  const { user, loading, isAuthenticated } = useAuth()

  if (loading) {
    return (
      <div className="center-screen">
        <div className="spinner" />
      </div>
    )
  }

  // Already signed in? Go straight to the right portal.
  if (isAuthenticated && user) {
    if (user.role === 'ADMIN') return <Navigate to="/admin" replace />
    if (user.role === 'MANAGER') return <Navigate to="/manager" replace />
    return <Navigate to="/consumer" replace />
  }

  return (
    <div className="landing">
      {/* ---------------------------------------------------------- Nav */}
      <header className="landing-nav">
        <div className="landing-nav-inner">
          <Link to="/" className="landing-brand">
            <span className="landing-brand-mark">
              <Icon name="car" size={20} />
            </span>
            <span className="landing-brand-text">
              <strong>SPMS</strong>
              <span>Smart Parking</span>
            </span>
          </Link>

          <nav className="landing-nav-links" aria-label="Landing">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <a href="#roles">Who it&apos;s for</a>
          </nav>

          <div className="landing-nav-actions">
            <Link to="/login" className="btn btn-outline btn-sm">
              Sign in
            </Link>
            <Link to="/register" className="btn btn-primary btn-sm">
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* ---------------------------------------------------------- Hero */}
      <section className="landing-hero">
        <div className="landing-hero-inner">
          <div className="landing-hero-copy">
            <span className="landing-pill">
              <Icon name="mapPin" size={14} /> Live availability across the city
            </span>

            <h1 className="landing-hero-title">
              Find, reserve and pay for parking in <span className="hl">seconds</span>.
            </h1>

            <p className="landing-hero-lead">
              SPMS connects drivers with real-time parking bays. Skip the circling, book your
              spot before you arrive, and drive straight in with a digital gate pass.
            </p>

            <div className="landing-hero-cta">
              <Link to="/register" className="btn btn-primary btn-lg">
                Create free account <Icon name="arrowRight" size={16} />
              </Link>
              <Link to="/login" className="btn btn-outline btn-lg">
                Sign in
              </Link>
            </div>

            <div className="landing-hero-note">
              <span>
                <Icon name="check" size={14} /> No card details stored
              </span>
              <span>
                <Icon name="check" size={14} /> Instant digital receipt
              </span>
            </div>
          </div>

          {/* Product mock — a digital gate pass */}
          <div className="landing-visual" aria-hidden="true">
            <div className="lv-card">
              <div className="lv-card-top">
                <span className="lv-lot">
                  <Icon name="building" size={15} /> Central Station · Level 2
                </span>
                <span className="lv-live">
                  <span className="lv-dot" /> Live
                </span>
              </div>

              <div className="lv-plate">KA 01 AB 1234</div>
              <div className="lv-slot">Slot B-204 · Covered</div>

              <div className="lv-divider" />

              <div className="lv-meta">
                <div>
                  <span>Window</span>
                  <strong>10:00 – 12:00</strong>
                </div>
                <div>
                  <span>Amount</span>
                  <strong>₹80.00</strong>
                </div>
              </div>

              <div className="lv-occ">
                <div className="lv-occ-head">
                  <span>Facility occupancy</span>
                  <span>68%</span>
                </div>
                <div className="occ-bar">
                  <div className="occ-seg occ-seg-occupied" style={{ width: '68%' }} />
                  <div className="occ-seg occ-seg-available" style={{ width: '32%' }} />
                </div>
              </div>

              <div className="lv-status">
                <Icon name="check" size={14} /> Payment confirmed · gate pass ready
              </div>
            </div>

            <div className="lv-chip lv-chip-1">
              <Icon name="mapPin" size={15} /> 12 lots nearby
            </div>
            <div className="lv-chip lv-chip-2">
              <Icon name="shield" size={15} /> Secure checkout
            </div>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- Capability strip */}
      <div className="landing-strip">
        <div className="landing-strip-item">
          <Icon name="search" size={20} />
          <div>
            Real-time bays
            <small>See what&apos;s free before you drive</small>
          </div>
        </div>
        <div className="landing-strip-item">
          <Icon name="shield" size={20} />
          <div>
            Secure payments
            <small>Cashless checkout, no card data stored</small>
          </div>
        </div>
        <div className="landing-strip-item">
          <Icon name="ticket" size={20} />
          <div>
            Digital pass
            <small>One reference gets you through the gate</small>
          </div>
        </div>
        <div className="landing-strip-item">
          <Icon name="chart" size={20} />
          <div>
            Operator insight
            <small>Occupancy, bookings & revenue reports</small>
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------- Features */}
      <section className="landing-section" id="features">
        <div className="landing-section-head">
          <p className="landing-eyebrow">Why SPMS</p>
          <h2 className="landing-section-title">Everything parking, in one place</h2>
          <p className="landing-section-lead">
            From the moment you search to the minute you drive out, the whole journey lives in a
            single app.
          </p>
        </div>

        <div className="landing-features">
          {FEATURES.map((f) => (
            <article className="landing-feature" key={f.title}>
              <div className="feature-icon">
                <Icon name={f.icon} size={20} />
              </div>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- How it works */}
      <div className="landing-band" id="how">
        <section className="landing-section">
          <div className="landing-section-head">
            <p className="landing-eyebrow">How it works</p>
            <h2 className="landing-section-title">Parked in three steps</h2>
            <p className="landing-section-lead">
              No app-switching, no phone calls, no cash at the barrier.
            </p>
          </div>

          <div className="landing-steps">
            {STEPS.map((s, i) => (
              <article className="landing-step" key={s.title}>
                <div className="landing-step-num">{i + 1}</div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
              </article>
            ))}
          </div>
        </section>
      </div>

      {/* ---------------------------------------------------------- Roles */}
      <section className="landing-section" id="roles">
        <div className="landing-section-head">
          <p className="landing-eyebrow">Who it&apos;s for</p>
          <h2 className="landing-section-title">Built for the whole operation</h2>
          <p className="landing-section-lead">
            Drivers, facility managers and platform administrators each get a purpose-built portal.
          </p>
        </div>

        <div className="landing-roles">
          {ROLES.map((r) => (
            <article className="landing-role" key={r.title}>
              <div className={`feature-icon ${r.tone}`.trim()}>
                <Icon name={r.icon} size={20} />
              </div>
              <h3>{r.title}</h3>
              <p>{r.body}</p>
              <div className="check-list">
                {r.points.map((p) => (
                  <div className="check-list-item" key={p}>
                    <Icon name="check" size={15} />
                    <span>{p}</span>
                  </div>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- CTA */}
      <section className="landing-cta">
        <div className="landing-cta-box">
          <h2>Ready to skip the search?</h2>
          <p>
            Create your account and reserve your first parking bay in under a minute.
          </p>
          <div className="landing-cta-actions">
            <Link to="/register" className="btn btn-primary btn-lg">
              Get started free <Icon name="arrowRight" size={16} />
            </Link>
            <Link to="/login" className="btn btn-outline btn-lg">
              I already have an account
            </Link>
          </div>
        </div>
      </section>

      {/* ---------------------------------------------------------- Footer */}
      <footer className="landing-footer">
        <div className="landing-footer-inner">
          <div className="landing-footer-brand">
            <span className="landing-brand-mark landing-brand-mark-sm">
              <Icon name="car" size={16} />
            </span>
            <span className="landing-footer-note">
              Smart Parking Management System
            </span>
          </div>

          <nav className="landing-footer-links" aria-label="Footer">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <Link to="/login">Sign in</Link>
            <Link to="/register">Create account</Link>
          </nav>

          <p className="landing-footer-note">© {new Date().getFullYear()} SPMS</p>
        </div>
      </footer>
    </div>
  )
}
