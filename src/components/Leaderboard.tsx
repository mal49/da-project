import { useEffect, useMemo, useState } from 'react'
import type { Player, RankingEntry } from '../players'
import { PLAYERS, fetchRankings } from '../players'
import { PlayerAvatar } from './PlayerAvatar'

type Props = {
  onPickPlayer: (player: Player) => void
}

type Status = 'loading' | 'live' | 'demo'
type Row = {
  player: Player
  rank: number
  points: number | null
  wins: number | null
  losses: number | null
  form: number[] | null
}

// Fallback flags for ranking entries that aren't in the static roster.
const FLAGS: Record<string, string> = {
  CHN: '🇨🇳', THA: '🇹🇭', DEN: '🇩🇰', FRA: '🇫🇷', INA: '🇮🇩', TPE: '🇹🇼',
  IND: '🇮🇳', MAS: '🇲🇾', SGP: '🇸🇬', JPN: '🇯🇵', KOR: '🇰🇷', ESP: '🇪🇸',
  HKG: '🇭🇰',
}

const byName = new Map(PLAYERS.map((p) => [p.name, p]))

// Resolve a ranking entry to a pickable Player: use the roster entry (for
// avatar/flag/hand + the predictor's metadata) but show the real BWF rank;
// synthesize a minimal Player if it isn't in the roster.
function toPlayer(e: RankingEntry, women: boolean): Player {
  const rostered = byName.get(e.name)
  if (rostered) return { ...rostered, rank: e.rank }
  return {
    id: e.name.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
    name: e.name,
    country: e.country,
    flag: FLAGS[e.country] ?? '🏳️',
    rank: e.rank,
    elo: e.elo ?? 2400,
    form: e.form ?? [],
    hand: 'R',
    height: 178,
    women,
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function Leaderboard({ onPickPlayer }: Props) {
  const [div, setDiv] = useState<'men' | 'women'>('men')
  const [men, setMen] = useState<RankingEntry[]>([])
  const [women, setWomen] = useState<RankingEntry[]>([])
  const [asOf, setAsOf] = useState('')
  const [source, setSource] = useState('')
  const [status, setStatus] = useState<Status>('loading')

  // Pull the official BWF ranking snapshot once; fall back to the static demo
  // roster if the backend is unreachable.
  useEffect(() => {
    let cancelled = false
    fetchRankings().then((data) => {
      if (cancelled) return
      if (data.available) {
        setMen(data.men)
        setWomen(data.women)
        setAsOf(data.asOf)
        setSource(data.source)
        setStatus('live')
      } else {
        setStatus('demo')
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const rows = useMemo<Row[]>(() => {
    if (status === 'live') {
      const entries = div === 'women' ? women : men
      return entries.slice(0, 8).map((e) => ({
        player: toPlayer(e, div === 'women'),
        rank: e.rank,
        points: e.points,
        wins: e.wins,
        losses: e.losses,
        form: e.form,
      }))
    }

    // Demo fallback (backend offline): static roster, fabricated record, no points.
    return PLAYERS.filter((p) => (div === 'women' ? p.women : !p.women))
      .slice()
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 8)
      .map((p) => {
        const wins = p.form.reduce((s, x) => s + x, 0)
        return { player: p, rank: p.rank, points: null, wins: 18 + wins * 3, losses: 9 - wins, form: p.form }
      })
  }, [div, status, men, women])

  const caption =
    status === 'loading'
      ? 'Loading rankings…'
      : status === 'live'
        ? `● Live World Rankings${asOf ? ` · as of ${formatDate(asOf)}` : ''}${source ? ` · ${source}` : ''}`
        : '○ Demo data — backend offline'

  return (
    <div>
      <div className="tabs" role="tablist">
        <button
          className="tab"
          role="tab"
          aria-selected={div === 'men'}
          onClick={() => setDiv('men')}
        >
          Men's Singles
        </button>
        <button
          className="tab"
          role="tab"
          aria-selected={div === 'women'}
          onClick={() => setDiv('women')}
        >
          Women's Singles
        </button>
      </div>
      <div className="lb-table">
        <div className="lb-row head">
          <span>Rank</span>
          <span>Player</span>
          <span>Points</span>
          <span>Record</span>
          <span>Last 5</span>
          <span />
        </div>
        {rows.length === 0 ? (
          <div className="lb-empty">
            {div === 'women'
              ? "Women's ranking snapshot pending — add it to backend/data/bwf_rankings.json."
              : 'No ranking data available.'}
          </div>
        ) : (
          rows.map(({ player: p, rank, points, wins, losses, form }, idx) => (
            <div className={`lb-row lb-rank-${idx + 1}`} key={p.id}>
              <span className="lb-rank">#{rank}</span>
              <span className="lb-name">
                <PlayerAvatar player={p} size={36} />
                <span>
                  <span>{p.name}</span>
                  <span className="country">
                    {p.country} · {p.hand}-HAND
                  </span>
                </span>
              </span>
              <span className="lb-elo">{points != null ? points.toLocaleString('en-US') : '—'}</span>
              <span className="lb-rec">
                {wins != null && losses != null ? (
                  <>
                    <strong>{wins}</strong>–{losses}
                  </>
                ) : (
                  '—'
                )}
              </span>
              <span className="lb-form">
                {form && form.length > 0
                  ? form.map((r, i) => (
                      <span key={i} className={`dot ${r ? 'w' : 'l'}`}>
                        {r ? 'W' : 'L'}
                      </span>
                    ))
                  : <span className="lb-form-na">—</span>}
              </span>
              <button className="lb-pick" onClick={() => onPickPlayer(p)}>
                Pick
              </button>
            </div>
          ))
        )}
      </div>
      <div className={`lb-caption ${status}`}>{caption}</div>
    </div>
  )
}
