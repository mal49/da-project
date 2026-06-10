export type NavTab = 'predict' | 'tournament' | 'rankings'

type Props = {
  apiOnline: boolean
  active: NavTab
  onNavigate: (tab: NavTab) => void
}

export function TopBar({ apiOnline, active, onNavigate }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="7" cy="17" r="2.6" fill="currentColor" stroke="none" />
            <path d="M9 15L19 5" />
            <path d="M9.6 16.2L21.5 8.5" />
            <path d="M7.8 14.4L15.5 2.5" />
            <path d="M15.5 2.5Q20 4 21.5 8.5" />
          </svg>
        </div>
        <div className="brand-name">
          shuttle<span>.ai</span>
        </div>
      </div>
      <nav className="top-nav">
        <button
          className={active === 'predict' ? 'active' : ''}
          onClick={() => onNavigate('predict')}
        >
          Predictor
        </button>
        <button
          className={active === 'tournament' ? 'active' : ''}
          onClick={() => onNavigate('tournament')}
        >
          Tournament
        </button>
        <button
          className={active === 'rankings' ? 'active' : ''}
          onClick={() => onNavigate('rankings')}
        >
          Rankings
        </button>
      </nav>
      <div className="top-actions">
        <span className={`api-pill${apiOnline ? '' : ' offline'}`}>
          <span className="dot" /> {apiOnline ? 'API LIVE' : 'API OFFLINE'}
        </span>
      </div>
    </header>
  )
}
