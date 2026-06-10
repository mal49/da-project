import { useEffect, useMemo, useState } from 'react'
import type { Discipline, Player, RankingEntry } from '../players'
import { PLAYERS, disciplineOf, fetchRankings } from '../players'
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

const DISCIPLINE_TABS: Discipline[] = ['MS', 'WS', 'MD', 'WD', 'XD']
const DISCIPLINE_LABEL: Record<Discipline, string> = {
  MS: "Men's Singles",
  WS: "Women's Singles",
  MD: "Men's Doubles",
  WD: "Women's Doubles",
  XD: 'Mixed Doubles',
}
const isPair = (d: Discipline): boolean => d === 'MD' || d === 'WD' || d === 'XD'

// Fallback flags for ranking entries that aren't in the static roster.
const FLAGS: Record<string, string> = {
  CHN: '🇨🇳', THA: '🇹🇭', DEN: '🇩🇰', FRA: '🇫🇷', INA: '🇮🇩', TPE: '🇹🇼',
  IND: '🇮🇳', MAS: '🇲🇾', SGP: '🇸🇬', JPN: '🇯🇵', KOR: '🇰🇷', ESP: '🇪🇸',
  HKG: '🇭🇰', GER: '🇩🇪', NED: '🇳🇱', CAN: '🇨🇦', USA: '🇺🇸', RUS: '🇷🇺',
}

// Order-/spacing-independent identity for a pair, so a Wikipedia pair name joins
// to the generated pool entry (which carries the real team Elo + avatar/flag).
function pairKey(name: string): string {
  return name
    .split(' / ')
    .map((m) => m.toLowerCase().replace(/[^a-z0-9]/g, ''))
    .sort()
    .join('|')
}

const byName = new Map(PLAYERS.map((p) => [p.name, p]))
const poolByPairKey = new Map(
  PLAYERS.filter((p) => isPair(disciplineOf(p))).map((p) => [pairKey(p.name), p]),
)

// Resolve a ranking entry to a pickable Player: reuse the roster/pool entry (for
// avatar/flag/hand + the predictor's real rating) but show the real BWF rank;
// synthesize a minimal Player when we have no match.
function toPlayer(e: RankingEntry, disc: Discipline): Player {
  if (isPair(disc)) {
    const pooled = poolByPairKey.get(pairKey(e.name))
    if (pooled) return { ...pooled, rank: e.rank }
  } else {
    const rostered = byName.get(e.name)
    if (rostered) return { ...rostered, rank: e.rank }
  }
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
    women: disc === 'WS' || disc === 'WD',
    discipline: disc,
  }
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function Leaderboard({ onPickPlayer }: Props) {
  const [disc, setDisc] = useState<Discipline>('MS')
  const [lists, setLists] = useState<Record<Discipline, RankingEntry[]>>({
    MS: [], WS: [], MD: [], WD: [], XD: [],
  })
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
        setLists({ MS: data.men, WS: data.women, MD: data.md, WD: data.wd, XD: data.xd })
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
      return (lists[disc] ?? []).slice(0, 8).map((e) => ({
        player: toPlayer(e, disc),
        rank: e.rank,
        points: e.points,
        wins: e.wins,
        losses: e.losses,
        form: e.form,
      }))
    }

    // Demo fallback (backend offline): static roster/pool, fabricated record.
    return PLAYERS.filter((p) => disciplineOf(p) === disc)
      .slice()
      .sort((a, b) => a.rank - b.rank)
      .slice(0, 8)
      .map((p) => {
        const wins = p.form.reduce((s, x) => s + x, 0)
        return { player: p, rank: p.rank, points: null, wins: 18 + wins * 3, losses: 9 - wins, form: p.form }
      })
  }, [disc, status, lists])

  const caption =
    status === 'loading'
      ? 'Loading rankings…'
      : status === 'live'
        ? `● Live World Rankings${asOf ? ` · as of ${formatDate(asOf)}` : ''}${source ? ` · ${source}` : ''}`
        : '○ Demo data · backend offline'

  return (
    <div>
      <div className="tabs" role="tablist" aria-label="Discipline">
        {DISCIPLINE_TABS.map((d) => (
          <button
            key={d}
            className="tab"
            role="tab"
            aria-selected={disc === d}
            onClick={() => setDisc(d)}
          >
            {DISCIPLINE_LABEL[d]}
          </button>
        ))}
      </div>
      <div className="lb-table">
        <div className="lb-row head">
          <span>Rank</span>
          <span>{isPair(disc) ? 'Pair' : 'Player'}</span>
          <span>Points</span>
          <span>Record</span>
          <span>Last 5</span>
          <span />
        </div>
        {rows.length === 0 ? (
          <div className="lb-empty">
            No {DISCIPLINE_LABEL[disc]} ranking data available. Refresh it with
            {' '}<code>python backend/fetch_wikipedia_rankings.py</code>.
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
                    {isPair(disc) ? `${p.country} · ${DISCIPLINE_LABEL[disc]}` : `${p.country} · ${p.hand}-HAND`}
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
