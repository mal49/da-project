type Props = {
  apiOnline: boolean
}

export function TopBar({ apiOnline }: Props) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="18" r="3" fill="currentColor" />
            <path d="M12 15 7 4" />
            <path d="M12 15l5-11" />
            <path d="M12 15v-11" opacity=".5" />
          </svg>
        </div>
        <div className="brand-name">
          shuttle<span>.ai</span>
        </div>
      </div>
      <nav className="top-nav">
        <a href="#predictor">Predictor</a>
        <a href="#rankings">Rankings</a>
        <a href="#api">API</a>
        <a href="#docs">Docs</a>
      </nav>
      <div className="top-actions">
        <span className={`api-pill${apiOnline ? '' : ' offline'}`}>
          <span className="dot" /> {apiOnline ? 'API LIVE' : 'API OFFLINE'}
        </span>
      </div>
    </header>
  )
}
