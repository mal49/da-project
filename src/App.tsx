import { useEffect, useRef, useState } from 'react'
import './App.css'
import type { MatchContext, Player, PredictionView, Round } from './players'
import {
  MATCHUPS,
  ROUNDS,
  SURFACES,
  buildPredictionView,
  findPlayer,
  lastName,
  matchTypeFor,
  roundToApi,
} from './players'
import { PlayerAvatar } from './components/PlayerAvatar'
import { PlayerModal } from './components/PlayerModal'
import { ResultCard } from './components/ResultCard'
import { Leaderboard } from './components/Leaderboard'
import { TopBar } from './components/TopBar'

type PredictionResponse = {
  player_a_win_probability: number
  player_b_win_probability: number
  predicted_winner: string
  confidence: string
  model_used: string
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

// ----- player slot button -----
function PlayerSlot({
  side,
  player,
  onClick,
}: {
  side: 'a' | 'b'
  player: Player | null
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
              <span className="accent">#{player.rank}</span>
              <span className="sep">·</span>
              <span>{player.elo} ELO</span>
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
  const [modal, setModal] = useState<'a' | 'b' | null>(null)
  const [showCtx, setShowCtx] = useState(false)
  const [ctx, setCtx] = useState<MatchContext>({
    tournament: '',
    round: 'QF',
    surface: 'Mat',
    bestOf: 3,
  })
  const [result, setResult] = useState<PredictionView | null>(null)
  const [predicting, setPredicting] = useState(false)
  const [error, setError] = useState('')
  const [leaderTarget, setLeaderTarget] = useState<'a' | 'b'>('a')
  const [apiOnline, setApiOnline] = useState(true)
  const resultRef = useRef<HTMLDivElement>(null)

  // Health check so the topbar pill reflects real backend reachability.
  useEffect(() => {
    let cancelled = false
    fetch(`${apiBaseUrl}/`)
      .then((res) => {
        if (!cancelled) setApiOnline(res.ok)
      })
      .catch(() => {
        if (!cancelled) setApiOnline(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

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

  function loadSample([aid, bid]: [string, string]) {
    setPA(findPlayer(aid) ?? null)
    setPB(findPlayer(bid) ?? null)
    setResult(null)
  }

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
      tournament_name: ctx.tournament.trim() || 'Unknown tournament',
      round: roundToApi(ctx.round),
      match_type: matchTypeFor(pA),
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
          ctx,
          data.player_a_win_probability,
          data.confidence,
          data.model_used,
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

  const ctxString = `${ctx.tournament || 'No tournament'} · ${ctx.round} · Best of ${ctx.bestOf}`

  return (
    <>
      <div className="bg-canvas" />
      <div className="page">
        <TopBar apiOnline={apiOnline} />

        <main className="container">
          <section className="hero" id="predictor">
            <span className="eyebrow">
              <span className="dot-pulse">●</span>
              Badminton AI Predictor · v2.1
            </span>
            <h1>
              Who wins
              <br />
              the <span className="accent">rally?</span>
            </h1>
            <p className="lede">
              Pick any two players from the world rankings. Our model crunches
              Elo, form, head-to-head and match context to call the winner — and
              the scoreline.
            </p>

            <div className="vs-shell">
              <div className="vs-bar">
                <PlayerSlot side="a" player={pA} onClick={() => setModal('a')} />
                <div className="vs-mid">
                  <span className="vs-glyph">VS</span>
                </div>
                <PlayerSlot side="b" player={pB} onClick={() => setModal('b')} />
              </div>

              <div className="vs-actions">
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    className={`ghost-btn ${showCtx ? 'open' : ''}`}
                    onClick={() => setShowCtx((v) => !v)}
                  >
                    {showCtx ? '− Hide context' : '+ Add match context'}
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m6 9 6 6 6-6" />
                    </svg>
                  </button>
                  <button className="ghost-btn" onClick={swap}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M7 16V4m0 0L3 8m4-4 4 4M17 8v12m0 0 4-4m-4 4-4-4" />
                    </svg>
                    Swap
                  </button>
                </div>
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

              {showCtx && (
                <div className="ctx-panel">
                  <div className="ctx-field">
                    <label>Tournament</label>
                    <input
                      value={ctx.tournament}
                      onChange={(e) => setCtx({ ...ctx, tournament: e.target.value })}
                      placeholder="All England Open"
                    />
                  </div>
                  <div className="ctx-field">
                    <label>Round</label>
                    <select
                      value={ctx.round}
                      onChange={(e) => setCtx({ ...ctx, round: e.target.value as Round })}
                    >
                      {ROUNDS.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="ctx-field">
                    <label>Surface</label>
                    <select
                      value={ctx.surface}
                      onChange={(e) =>
                        setCtx({ ...ctx, surface: e.target.value as MatchContext['surface'] })
                      }
                    >
                      {SURFACES.map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="ctx-field">
                    <label>Best of</label>
                    <select
                      value={ctx.bestOf}
                      onChange={(e) =>
                        setCtx({ ...ctx, bestOf: Number(e.target.value) as 3 | 5 })
                      }
                    >
                      <option value={3}>3 sets</option>
                      <option value={5}>5 sets</option>
                    </select>
                  </div>
                </div>
              )}

              {/* sample matchups */}
              <div className="chip-row">
                <span className="chip-label">Try these →</span>
                {MATCHUPS.map(([aid, bid], i) => {
                  const a = findPlayer(aid)
                  const b = findPlayer(bid)
                  if (!a || !b) return null
                  return (
                    <button key={i} className="chip" onClick={() => loadSample([aid, bid])}>
                      <span className="flag">{a.flag}</span>
                      <span>{lastName(a.name)}</span>
                      <span className="vs">VS</span>
                      <span>{lastName(b.name)}</span>
                      <span className="flag">{b.flag}</span>
                    </button>
                  )
                })}
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
        </main>

        <footer>
          <span>© 2026 shuttle.ai · Model v2.1 trained on 18,400 BWF matches</span>
          <span className="right">{ctxString}</span>
        </footer>
      </div>

      <PlayerModal
        open={modal !== null}
        excludeId={modal === 'a' ? pB?.id : pA?.id}
        title={modal === 'a' ? 'Search Player A' : 'Search Player B'}
        onPick={handlePick}
        onClose={() => setModal(null)}
      />
    </>
  )
}

export default App
