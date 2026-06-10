import { useEffect, useRef, useState } from 'react'
import './App.css'
import type { Discipline, Player, PredictionView, RealStats } from './players'
import {
  PLAYERS,
  buildPredictionView,
  disciplineOf,
  fetchLeaderboard,
  findPlayer,
  lastName,
  roundToApi,
} from './players'
import { PlayerAvatar } from './components/PlayerAvatar'
import { PlayerModal } from './components/PlayerModal'
import { ResultCard } from './components/ResultCard'
import { Leaderboard } from './components/Leaderboard'
import { TopBar, type NavTab } from './components/TopBar'
import { TournamentSimulator } from './components/TournamentSimulator'

type PredictionResponse = {
  player_a_win_probability: number
  player_b_win_probability: number
  predicted_winner: string
  confidence: string
  model_used: string
}

type ModelInfo = {
  model_label?: string
  matches_trained?: number
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const DISCIPLINE_TABS: Discipline[] = ['MS', 'WS', 'MD', 'WD', 'XD']
const DISCIPLINE_LABEL: Record<Discipline, string> = {
  MS: "Men's Singles",
  WS: "Women's Singles",
  MD: "Men's Doubles",
  WD: "Women's Doubles",
  XD: 'Mixed Doubles',
}
const isPair = (d: Discipline): boolean => d === 'MD' || d === 'WD' || d === 'XD'

// Top N entrants of a discipline from the pool, by rank — used for the default
// slots and the "Try these" samples when a discipline is selected.
function topOf(d: Discipline, n: number): Player[] {
  return PLAYERS.filter((p) => disciplineOf(p) === d)
    .slice()
    .sort((a, b) => a.rank - b.rank)
    .slice(0, n)
}

// Compact chip label: a singles surname, or the two surnames of a pair ('Kim/Seo').
function chipName(p: Player): string {
  return isPair(disciplineOf(p))
    ? p.name.split(' / ').map((m) => m.split(' ')[0]).join('/')
    : lastName(p.name)
}

// A few sample matchups for the current discipline, drawn from the top of the pool.
function samplesFor(d: Discipline): [Player, Player][] {
  const top = topOf(d, 6)
  const out: [Player, Player][] = []
  for (const [i, j] of [[0, 1], [2, 3], [0, 4]] as const) {
    if (top[i] && top[j]) out.push([top[i], top[j]])
  }
  return out
}

// ----- player slot button -----
function PlayerSlot({
  side,
  player,
  realElo,
  realRank,
  onClick,
}: {
  side: 'a' | 'b'
  player: Player | null
  realElo: number | null
  realRank: number | null
  onClick: () => void
}) {
  const right = side === 'b'
  return (
    <button className={`pslot ${right ? 'right' : ''}`} onClick={onClick}>
      {player ? (
        <PlayerAvatar player={player} size={56} />
      ) : (
        <div className="pavatar empty">+</div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="label">Player {right ? 'B' : 'A'}</div>
        {player ? (
          <>
            <div className="name">{player.name}</div>
            <div className="meta">
              <span className="accent">#{realRank ?? player.rank}</span>
              <span className="sep">·</span>
              <span>{realElo != null ? `${realElo} ELO` : 'Unrated'}</span>
              <span className="sep">·</span>
              <span>{player.country}</span>
            </div>
          </>
        ) : (
          <>
            <div className="name placeholder">Select a player…</div>
            <div className="meta">
              <span>Click to search the world rankings</span>
            </div>
          </>
        )}
      </div>
    </button>
  )
}

function App() {
  const [pA, setPA] = useState<Player | null>(findPlayer('va') ?? null)
  const [pB, setPB] = useState<Player | null>(findPlayer('kv') ?? null)
  const [discipline, setDiscipline] = useState<Discipline>('MS')
  const [modal, setModal] = useState<'a' | 'b' | null>(null)
  // Active navbar tab. Predictor and Rankings are both sections of the predictor
  // view; Tournament is its own view.
  const [navTab, setNavTab] = useState<NavTab>('predict')
  const view = navTab === 'tournament' ? 'tournament' : 'predict'
  const [result, setResult] = useState<PredictionView | null>(null)
  const [predicting, setPredicting] = useState(false)
  const [error, setError] = useState('')
  const [leaderTarget, setLeaderTarget] = useState<'a' | 'b'>('a')
  const [apiOnline, setApiOnline] = useState(true)
  // Real match-derived Elo (from /players), keyed by player name. Players we have
  // no ingested history for are absent -> shown as "Unrated" (never a fake number).
  const [realStats, setRealStats] = useState<Map<string, RealStats>>(new Map())
  // Live model info (name + match count) for the footer, from the API root.
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  // Health check (topbar pill) + model info (footer), both from the API root.
  useEffect(() => {
    let cancelled = false
    fetch(`${apiBaseUrl}/`)
      .then(async (res) => {
        if (cancelled) return
        setApiOnline(res.ok)
        if (res.ok) {
          try {
            setModelInfo((await res.json()) as ModelInfo)
          } catch {
            /* ignore malformed body */
          }
        }
      })
      .catch(() => {
        if (!cancelled) setApiOnline(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Pull the real Elo/record/form ladder once, so the UI shows true ratings.
  useEffect(() => {
    let cancelled = false
    fetchLeaderboard().then((data) => {
      if (!cancelled && data.available) setRealStats(data.stats)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Real Elo / world rank for a player name, or null when they're unrated.
  const eloFor = (name: string): number | null => realStats.get(name)?.elo ?? null
  const rankFor = (name: string): number | null => realStats.get(name)?.rank ?? null

  // Scroll-spy: while in the predictor view, highlight "Rankings" in the navbar
  // whenever the rankings section occupies the middle of the viewport.
  useEffect(() => {
    if (view !== 'predict') return
    const el = document.getElementById('rankings')
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => {
        setNavTab((cur) =>
          cur === 'tournament' ? cur : entry.isIntersecting ? 'rankings' : 'predict',
        )
      },
      { rootMargin: '-35% 0px -45% 0px' },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [view])

  // Navbar click: switch view and/or scroll to the right section.
  function navigate(tab: NavTab) {
    const fromTournament = view === 'tournament'
    setNavTab(tab)
    if (tab === 'tournament') return
    // Predictor and Rankings live in the predictor view; if we're coming from
    // the tournament view, wait a tick for it to render before scrolling.
    setTimeout(() => {
      if (tab === 'rankings') {
        document.getElementById('rankings')?.scrollIntoView({ behavior: 'smooth' })
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }
    }, fromTournament ? 60 : 0)
  }

  function handlePick(player: Player) {
    if (modal === 'a') setPA(player)
    if (modal === 'b') setPB(player)
    setModal(null)
    setResult(null)
  }

  function swap() {
    setPA(pB)
    setPB(pA)
    setResult(null)
  }

  function loadSample(a: Player, b: Player) {
    setPA(a)
    setPB(b)
    setResult(null)
  }

  // Random matchup: two distinct entrants from the current discipline pool.
  function randomMatchup() {
    const pool = PLAYERS.filter((p) => disciplineOf(p) === discipline)
    if (pool.length < 2) return
    const i = Math.floor(Math.random() * pool.length)
    let j = Math.floor(Math.random() * (pool.length - 1))
    if (j >= i) j++
    loadSample(pool[i], pool[j])
  }

  // Switch discipline: reset both slots to the top two entrants of that discipline
  // so the predictor always holds a valid same-discipline matchup.
  function changeDiscipline(d: Discipline) {
    setDiscipline(d)
    const [a, b] = topOf(d, 2)
    setPA(a ?? null)
    setPB(b ?? null)
    setResult(null)
    setError('')
  }

  const samples = samplesFor(discipline)

  async function runPredict() {
    if (!pA || !pB) return
    setPredicting(true)
    setResult(null)
    setError('')

    const payload = {
      player_a_name: pA.name,
      player_b_name: pB.name,
      player_a_rank: pA.rank,
      player_b_rank: pB.rank,
      player_a_elo: pA.elo,
      player_b_elo: pB.elo,
      tournament_name: 'Unknown tournament',
      round: roundToApi('QF'),
      match_type: discipline,
    }

    try {
      const res = await fetch(`${apiBaseUrl}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { detail?: string } | null
        throw new Error(body?.detail ?? `Request failed with ${res.status}`)
      }
      const data = (await res.json()) as PredictionResponse
      setApiOnline(true)
      setResult(
        buildPredictionView(
          pA,
          pB,
          data.player_a_win_probability,
          data.confidence,
          data.model_used,
          eloFor(pA.name),
          eloFor(pB.name),
          rankFor(pA.name),
          rankFor(pB.name),
        ),
      )
      setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 100)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to reach the prediction API.')
    } finally {
      setPredicting(false)
    }
  }

  return (
    <>
      <div className="bg-canvas" />
      <div className="page">
        <TopBar apiOnline={apiOnline} active={navTab} onNavigate={navigate} />

        <main className="container">
          {view === 'tournament' ? (
            <TournamentSimulator eloFor={eloFor} rankFor={rankFor} />
          ) : (
          <>
          <section className="hero" id="predictor">
            <h1>
              Who wins
              <br />
              the <span className="accent">rally?</span>
            </h1>
            <p className="lede">
              Pick any matchup from the world rankings, singles or doubles. The
              model weighs Elo ratings, recent form, head-to-head record and match
              context to call the winner and the scoreline.
            </p>

            <div className="vs-disc">
              <div className="tabs" role="tablist" aria-label="Discipline">
                {DISCIPLINE_TABS.map((d) => (
                  <button
                    key={d}
                    className="tab"
                    role="tab"
                    aria-selected={discipline === d}
                    onClick={() => changeDiscipline(d)}
                  >
                    <span className="tab-l">{DISCIPLINE_LABEL[d]}</span>
                    <span className="tab-s">{d}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="vs-shell">
              <div className="vs-bar">
                <PlayerSlot
                  side="a"
                  player={pA}
                  realElo={pA ? eloFor(pA.name) : null}
                  realRank={pA ? rankFor(pA.name) : null}
                  onClick={() => setModal('a')}
                />
                <div className="vs-mid">
                  <span className="vs-glyph">VS</span>
                  <button
                    className="swap-btn"
                    onClick={swap}
                    title="Swap sides"
                    aria-label="Swap sides"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M8 3 4 7l4 4" />
                      <path d="M4 7h16" />
                      <path d="m16 21 4-4-4-4" />
                      <path d="M20 17H4" />
                    </svg>
                  </button>
                </div>
                <PlayerSlot
                  side="b"
                  player={pB}
                  realElo={pB ? eloFor(pB.name) : null}
                  realRank={pB ? rankFor(pB.name) : null}
                  onClick={() => setModal('b')}
                />
              </div>

              <div className="vs-actions">
                <button
                  className="predict-btn"
                  onClick={runPredict}
                  disabled={!pA || !pB || predicting}
                >
                  {predicting ? 'Crunching…' : 'Predict winner'}
                  <svg
                    className="arrow"
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                  >
                    <path d="M5 12h14m-6-6 6 6-6 6" />
                  </svg>
                </button>
              </div>

              {/* sample matchups for the selected discipline */}
              <div className="chip-row">
                <span className="chip-label">Try these →</span>
                {samples.map(([a, b], i) => (
                  <button key={i} className="chip" onClick={() => loadSample(a, b)}>
                    <span className="flag">{a.flag}</span>
                    <span>{chipName(a)}</span>
                    <span className="vs">VS</span>
                    <span>{chipName(b)}</span>
                    <span className="flag">{b.flag}</span>
                  </button>
                ))}
                <button className="chip chip-random" onClick={randomMatchup}>
                  <svg
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.8-1.1 2-1.7 3.3-1.7H22" />
                    <path d="m18 2 4 4-4 4" />
                    <path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2" />
                    <path d="M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8" />
                    <path d="m18 14 4 4-4 4" />
                  </svg>
                  Random
                </button>
              </div>

              {/* result reveal */}
              <div ref={resultRef} className="result-shell" data-open={result ? 'true' : 'false'}>
                {result && pA && pB && <ResultCard result={result} a={pA} b={pB} />}
              </div>

              {error && <div className="result-error">{error}</div>}
            </div>
          </section>

          <section className="section" id="rankings">
            <div className="section-head">
              <div>
                <div className="kicker">◆ Live BWF World Rankings</div>
                <h2>
                  Top of the <span className="accent">ladder</span>
                </h2>
              </div>
              <div className="right">
                Pick into slot <span className="slot-tag">{leaderTarget === 'a' ? 'A' : 'B'}</span> →
                <button
                  className="ghost-btn"
                  onClick={() => setLeaderTarget(leaderTarget === 'a' ? 'b' : 'a')}
                >
                  Switch to {leaderTarget === 'a' ? 'B' : 'A'}
                </button>
              </div>
            </div>
            <Leaderboard
              onPickPlayer={(p) => {
                if (leaderTarget === 'a') setPA(p)
                else setPB(p)
                setResult(null)
                window.scrollTo({ top: 0, behavior: 'smooth' })
              }}
            />
          </section>
          </>
          )}
        </main>

        <footer>
          <span>
            © 2026 shuttle.ai ·{' '}
            {modelInfo?.matches_trained
              ? `${modelInfo.model_label ?? 'ML'} model · trained on ${modelInfo.matches_trained.toLocaleString()} BWF matches across all disciplines (2021–26)`
              : 'badminton match predictor'}
          </span>
        </footer>
      </div>

      <PlayerModal
        open={modal !== null}
        excludeId={modal === 'a' ? pB?.id : pA?.id}
        title={modal === 'a' ? 'Search Player A' : 'Search Player B'}
        discipline={discipline}
        eloFor={eloFor}
        rankFor={rankFor}
        onPick={handlePick}
        onClose={() => setModal(null)}
      />
    </>
  )
}

export default App
