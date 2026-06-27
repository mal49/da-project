import { useState } from 'react'

export type NavTab = 'predict' | 'tournament' | 'rankings'

type Props = {
  apiOnline: boolean
  active: NavTab
  onNavigate: (tab: NavTab) => void
}

export function TopBar({ apiOnline, active, onNavigate }: Props) {
  const [menuOpen, setMenuOpen] = useState(false)

  // Close the mobile dropdown whenever a destination is picked.
  const go = (tab: NavTab) => {
    setMenuOpen(false)
    onNavigate(tab)
  }

  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <img src="/badminton-logo.svg" alt="shuttle.ai logo" width="30" height="30" />
        </div>
        <div className="brand-name">
          shuttle<span>.ai</span>
        </div>
      </div>
      <nav className={`top-nav${menuOpen ? ' open' : ''}`}>
        <button
          className={active === 'predict' ? 'active' : ''}
          onClick={() => go('predict')}
        >
          Predictor
        </button>
        <button
          className={active === 'tournament' ? 'active' : ''}
          onClick={() => go('tournament')}
        >
          Tournament
        </button>
        <button
          className={active === 'rankings' ? 'active' : ''}
          onClick={() => go('rankings')}
        >
          Rankings
        </button>
      </nav>
      <div className="top-actions">
        <span className={`api-pill${apiOnline ? '' : ' offline'}`}>
          <span className="dot" /> {apiOnline ? 'API LIVE' : 'API OFFLINE'}
        </span>
        <button
          className="nav-burger"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((o) => !o)}
        >
          {menuOpen ? (
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          ) : (
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}
