import { useEffect, useMemo, useState } from 'react'
import type { Discipline, Player, RankingEntry, TournamentResult } from '../players'
import {
  PLAYERS,
  disciplineOf,
  fetchRankings,
  lastName,
  seedOrder,
  simulateTournament,
} from '../players'
import { PlayerAvatar } from './PlayerAvatar'
import { PlayerModal } from './PlayerModal'

type DrawSize = 8 | 16 | 32

const SIZES: DrawSize[] = [8, 16, 32]

// Discipline tabs. Singles seed from the live BWF rankings; doubles/mixed seed
// from the generated pair pool (no public BWF doubles ranking is wired up).
const DISCIPLINE_TABS: Discipline[] = ['MS', 'WS', 'MD', 'WD', 'XD']
const DISCIPLINE_LABEL: Record<Discipline, string> = {
  MS: "Men's Singles",
  WS: "Women's Singles",
  MD: "Men's Doubles",
  WD: "Women's Doubles",
  XD: 'Mixed Doubles',
}
const EMPTY_POOLS: Record<Discipline, Player[]> = { MS: [], WS: [], MD: [], WD: [], XD: [] }
const isPair = (d: Discipline): boolean => d === 'MD' || d === 'WD' || d === 'XD'

// Short round code for a column header, keyed by how many players are still in it.
const SHORT_CODE: Record<number, string> = { 32: 'R32', 16: 'R16', 8: 'QF', 4: 'SF', 2: 'F' }

// Fallback flags for ranking entries that aren't in the static roster.
const FLAGS: Record<string, string> = {
  CHN: '🇨🇳', THA: '🇹🇭', DEN: '🇩🇰', FRA: '🇫🇷', INA: '🇮🇩', TPE: '🇹🇼',
  IND: '🇮🇳', MAS: '🇲🇾', SGP: '🇸🇬', JPN: '🇯🇵', KOR: '🇰🇷', ESP: '🇪🇸', HKG: '🇭🇰',
}

const rosterByName = new Map(PLAYERS.map((p) => [p.name, p]))

// Resolve a ranking entry to a pickable Player (roster entry for avatar/metadata,
// synthesized otherwise), carrying the real BWF rank.
function entryToPlayer(e: RankingEntry, women: boolean): Player {
  const rostered = rosterByName.get(e.name)
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

type Props = {
  eloFor: (name: string) => number | null
  rankFor: (name: string) => number | null
}

// One name line inside a match card. Carries enough context to render an empty
// pick slot, a seeded entrant, or a decided result (winner highlighted).
type Slot = {
  player: Player | null
  seed?: number // 1-indexed seed, only on the first (editable) round
  seedIndex?: number // 0-indexed slot to edit when clicked
  editable?: boolean
  prob?: number
  isWinner?: boolean
  decided?: boolean // a result exists for this match
  placeholder?: string
}
// A bracket cell: a normal match has two slots; the winner cell has one.
type Cell = { a: Slot; b?: Slot }
type Column = { head: string; kind: 'match' | 'winner'; cells: Cell[]; revealed: boolean }

export function TournamentSimulator({ eloFor, rankFor }: Props) {
  const [discipline, setDiscipline] = useState<Discipline>('MS')
  const [requestedSize, setRequestedSize] = useState<DrawSize>(16)
  // Per-seed user overrides (seed index -> player); everything else auto-seeds
  // from the ranking pool, so the draw is fully derived (no setState in effects).
  const [overrides, setOverrides] = useState<Record<number, Player>>({})
  const [pools, setPools] = useState<Record<Discipline, Player[]>>(EMPTY_POOLS)
  const [editing, setEditing] = useState<number | null>(null)
  const [result, setResult] = useState<TournamentResult | null>(null)
  // How many bracket columns have been "played out" — drives the round-by-round
  // reveal animation after a result lands.
  const [reveal, setReveal] = useState(0)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  // Build each discipline's entrant pool. Doubles/mixed pairs come straight from
  // the generated pool (PLAYERS), sorted by their real pair rank. Singles also
  // fold in the live BWF rankings (real order) when the backend is reachable.
  // (setState here is async — allowed.)
  useEffect(() => {
    let cancelled = false
    const byDiscipline = (d: Discipline): Player[] =>
      PLAYERS.filter((p) => disciplineOf(p) === d).slice().sort((a, b) => a.rank - b.rank)
    const base: Record<Discipline, Player[]> = {
      MS: byDiscipline('MS'),
      WS: byDiscipline('WS'),
      MD: byDiscipline('MD'),
      WD: byDiscipline('WD'),
      XD: byDiscipline('XD'),
    }
    // Merge BWF ranking entries (singles only) ahead of the static roster.
    const withRankings = (entries: RankingEntry[], d: Discipline): Player[] => {
      const seen = new Set<string>()
      const out: Player[] = []
      for (const e of entries) {
        const p = entryToPlayer(e, d === 'WS')
        if (!seen.has(p.name)) {
          seen.add(p.name)
          out.push(p)
        }
      }
      for (const p of base[d]) {
        if (!seen.has(p.name)) {
          seen.add(p.name)
          out.push(p)
        }
      }
      return out.sort((a, b) => a.rank - b.rank)
    }
    fetchRankings().then((data) => {
      if (cancelled) return
      if (data.available) {
        setPools({ ...base, MS: withRankings(data.men, 'MS'), WS: withRankings(data.women, 'WS') })
      } else {
        setPools(base)
      }
    })
    return () => {
      cancelled = true
    }
  }, [])

  const pool = pools[discipline]

  // Largest power-of-two draw the current pool can fill (capped at 32), and the
  // effective size = the requested size clamped to what the pool supports.
  const maxSize = useMemo(() => {
    let m = 1
    while (m * 2 <= Math.min(pool.length, 32)) m *= 2
    return m
  }, [pool.length])
  const size = Math.min(requestedSize, maxSize)

  // The draw is derived: each seed is the user's override, else the pool seed.
  const entrants = useMemo<(Player | null)[]>(() => {
    const slots: (Player | null)[] = []
    for (let i = 0; i < size; i++) slots.push(overrides[i] ?? pool[i] ?? null)
    return slots
  }, [size, pool, overrides])

  function changeDiscipline(d: Discipline) {
    setDiscipline(d)
    setOverrides({})
    setResult(null)
    setError('')
  }

  function changeSize(s: DrawSize) {
    setRequestedSize(s)
    setResult(null)
    setError('')
  }

  function autoSeed() {
    setOverrides({})
    setResult(null)
    setError('')
  }

  // Fill every slot with random distinct players from the pool (Fisher–Yates).
  function randomSeed() {
    const deck = [...pool]
    for (let i = deck.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[deck[i], deck[j]] = [deck[j], deck[i]]
    }
    const next: Record<number, Player> = {}
    deck.slice(0, size).forEach((p, i) => {
      next[i] = p
    })
    setOverrides(next)
    setResult(null)
    setReveal(0)
    setError('')
  }

  function handlePick(player: Player) {
    if (editing == null) return
    const slot = editing
    setOverrides((prev) => ({ ...prev, [slot]: player }))
    setEditing(null)
    setResult(null)
  }

  const filled = entrants.filter((p): p is Player => p != null).length
  const ready = filled === size && size >= 2

  async function run() {
    if (!ready) return
    setRunning(true)
    setError('')
    setResult(null)
    setReveal(0)
    // Arrange entrants (index 0 = seed 1) into bracket-slot order, then send.
    const arranged = seedOrder(size)
      .map((seed) => entrants[seed - 1])
      .filter((p): p is Player => p != null)
    const seeded = arranged.map((p) => ({
      name: p.name,
      rank: rankFor(p.name) ?? p.rank,
      elo: eloFor(p.name) ?? p.elo,
    }))
    const res = await simulateTournament(seeded, discipline, 'BWF World Tour')
    if (res.available) {
      // The reveal effect plays the rounds out, then clears `running`.
      setResult(res)
    } else {
      setError(res.error ?? 'Unable to reach the simulator.')
      setRunning(false)
    }
  }

  // Map a player name (from the bracket result) back to a Player for display.
  const nameToPlayer = useMemo(() => {
    const m = new Map<string, Player>()
    for (const p of entrants) if (p) m.set(p.name, p)
    for (const p of pool) if (!m.has(p.name)) m.set(p.name, p)
    return m
  }, [entrants, pool])

  const championPlayer = result ? nameToPlayer.get(result.champion) : undefined

  // Once a result lands, step the reveal forward one column at a time so the
  // bracket "plays out" — each round's winners advance and percentages animate
  // in — then clear the running flag when the champion is reached.
  useEffect(() => {
    if (!result) return
    // `run()` resets reveal to 0 before the fetch, so we just step it forward
    // here (in timers, not synchronously) until the champion is shown.
    const total = result.rounds.length + 1 // match rounds + winner
    const timers: ReturnType<typeof setTimeout>[] = []
    let step = 0
    const advance = () => {
      step += 1
      setReveal(step)
      if (step < total) timers.push(setTimeout(advance, 750))
      else setRunning(false)
    }
    timers.push(setTimeout(advance, 300))
    return () => timers.forEach(clearTimeout)
  }, [result])

  // Derive the full bracket as columns of cells: round 0 is the editable draw
  // (built from the seed slotting), later rounds fill from the result as it is
  // revealed (else empty placeholders), and a final Winner column.
  const columns = useMemo<Column[]>(() => {
    if (size < 2) return []
    const order = seedOrder(size)
    const rounds = Math.round(Math.log2(size))
    const cols: Column[] = []

    for (let c = 0; c < rounds; c++) {
      const cards = size / 2 ** (c + 1)
      const playersInRound = size / 2 ** c
      const head = SHORT_CODE[playersInRound] ?? `R${playersInRound}`
      const revealed = Boolean(result) && c < reveal
      const rRound = revealed ? result?.rounds[c] : undefined
      const cells: Cell[] = []
      for (let i = 0; i < cards; i++) {
        if (c === 0) {
          // First round: seeded entrants, clickable to choose a player.
          const topSeed = order[2 * i]
          const botSeed = order[2 * i + 1]
          const topP = entrants[topSeed - 1] ?? null
          const botP = entrants[botSeed - 1] ?? null
          const m = rRound?.matches[i]
          cells.push({
            a: {
              player: topP,
              seed: topSeed,
              seedIndex: topSeed - 1,
              editable: true,
              prob: m?.prob_a,
              isWinner: m ? m.winner === topP?.name : false,
              decided: Boolean(m),
            },
            b: {
              player: botP,
              seed: botSeed,
              seedIndex: botSeed - 1,
              editable: true,
              prob: m?.prob_b,
              isWinner: m ? m.winner === botP?.name : false,
              decided: Boolean(m),
            },
          })
        } else if (rRound) {
          // Later round with a result: the winners that advanced.
          const m = rRound.matches[i]
          cells.push({
            a: {
              player: nameToPlayer.get(m.player_a) ?? null,
              prob: m.prob_a,
              isWinner: m.winner === m.player_a,
              decided: true,
            },
            b: {
              player: nameToPlayer.get(m.player_b) ?? null,
              prob: m.prob_b,
              isWinner: m.winner === m.player_b,
              decided: true,
            },
          })
        } else {
          // Later round, not yet simulated: empty slots awaiting winners.
          cells.push({ a: { player: null, placeholder: '—' }, b: { player: null, placeholder: '—' } })
        }
      }
      cols.push({ head, kind: 'match', cells, revealed })
    }

    const winnerRevealed = Boolean(result) && reveal > rounds
    cols.push({
      head: 'Winner',
      kind: 'winner',
      revealed: winnerRevealed,
      cells: [
        {
          a: {
            player: winnerRevealed ? (championPlayer ?? null) : null,
            isWinner: winnerRevealed,
            decided: winnerRevealed,
            placeholder: 'Winner',
          },
        },
      ],
    })
    return cols
  }, [size, entrants, result, reveal, nameToPlayer, championPlayer])

  return (
    <section className="section" id="tournament">
      <div className="section-head">
        <div>
          <div className="kicker">◆ Bracket Simulator</div>
          <h2>
            Who lifts the <span className="accent">title?</span>
          </h2>
        </div>
        <div className="right">Seed a draw, then let the model play every match to a champion</div>
      </div>

      <div className="sim-toolbar">
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
        <div className="tabs" role="tablist" aria-label="Draw size">
          {SIZES.map((s) => (
            <button
              key={s}
              className="tab"
              role="tab"
              aria-selected={size === s}
              disabled={s > maxSize}
              onClick={() => changeSize(s)}
            >
              {SHORT_CODE[s]} · {s}
            </button>
          ))}
        </div>
        <div className="sim-actions">
          <button className="ghost-btn" onClick={autoSeed}>
            Auto-seed top {size}
          </button>
          <button className="ghost-btn" onClick={randomSeed} disabled={pool.length < size}>
            🎲 Random draw
          </button>
          <button className="predict-btn" onClick={run} disabled={!ready || running}>
            {running ? (
              <span className="btn-loading">
                <span className="btn-spinner" aria-hidden="true" />
                Simulating…
              </span>
            ) : (
              'Simulate tournament'
            )}
          </button>
        </div>
      </div>

      {!ready && (
        <div className="sim-note">
          {filled < size
            ? `Seed ${size - filled} more ${DISCIPLINE_LABEL[discipline]} ` +
              `${isPair(discipline) ? 'pair' : 'player'}${size - filled > 1 ? 's' : ''} to fill the draw.`
            : 'Pick entrants to seed the draw.'}
        </div>
      )}

      {error && <div className="result-error">{error}</div>}

      {columns.length > 0 && (
        <>
          <p className="tbracket-hint">
            Click any seed in the first column to choose a player, then simulate to fill the bracket.
          </p>
          <div className="tbracket-wrap">
            {running && !result && (
              <div className="tbracket-loading" role="status" aria-live="polite">
                <span className="tspinner" aria-hidden="true" />
                <span className="tbracket-loading-text">Simulating tournament…</span>
              </div>
            )}
            <div className="tbracket">
              {columns.map((col, ci) => {
                const single = col.kind === 'match' && col.cells.length === 1
                const isWinner = col.kind === 'winner'
                return (
                  <div className={`tcol${isWinner ? ' tcol--winner' : ''}`} key={ci}>
                    <div className="tcol-head">
                      {isWinner ? (
                        <span className="tcol-trophy">🏆 Winner</span>
                      ) : (
                        <span className="rcode">{col.head}</span>
                      )}
                    </div>
                    {col.cells.map((cell, i) => {
                      // Connector classes drive the elbow lines (see CSS).
                      let conn = ''
                      if (isWinner) conn = 'tmatch--in'
                      else {
                        if (ci >= 1) conn = 'tmatch--in'
                        if (single) conn += ' tmatch--straight'
                        else conn += i % 2 === 0 ? ' tmatch--top' : ' tmatch--bottom'
                      }
                      // Later rounds and the winner remount when revealed so their
                      // entrance animation (the "advancing" slide / pop) replays;
                      // round 0 stays put and just animates its numbers in place.
                      const animates = isWinner || ci >= 1
                      const key = animates ? `${i}-${col.revealed ? 'r' : 'p'}` : i
                      const enter = col.revealed && ci >= 1 && !isWinner ? ' is-enter' : ''
                      const pending = running && !col.revealed && ci >= 1 && !isWinner ? ' is-pending' : ''
                      return (
                        <div className={`tmatch ${conn}`} key={key}>
                          {isWinner ? (
                            <WinnerCard slot={cell.a} />
                          ) : (
                            <div className={`tcard${enter}${pending}`}>
                              <SlotRow slot={cell.a} onEdit={setEditing} />
                              {cell.b && <SlotRow slot={cell.b} onEdit={setEditing} />}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}

      <PlayerModal
        open={editing !== null}
        title={`Seed ${(editing ?? 0) + 1}: search ${isPair(discipline) ? 'pairs' : 'players'}`}
        discipline={discipline}
        eloFor={eloFor}
        rankFor={rankFor}
        onPick={handlePick}
        onClose={() => setEditing(null)}
      />
    </section>
  )
}

// A win-probability label that counts up from an even 50% to its final value
// when it mounts (i.e. when its round is revealed), so the odds appear to resolve.
function Pct({ value }: { value: number }) {
  const target = value * 100
  const [shown, setShown] = useState(50)
  useEffect(() => {
    let raf = 0
    const duration = 650
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3) // easeOutCubic
      setShown(50 + (target - 50) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target])
  return <span className="ts-prob">{Math.round(shown)}%</span>
}

function SlotRow({ slot, onEdit }: { slot: Slot; onEdit: (seedIndex: number) => void }) {
  const cls = `ts-row${slot.decided ? (slot.isWinner ? ' win' : ' lose') : ''}`
  const inner = (
    <>
      {slot.seed != null && <span className="ts-seed">{slot.seed}</span>}
      {slot.player ? (
        <>
          <PlayerAvatar player={slot.player} size={24} />
          <span className="ts-name">{lastName(slot.player.name)}</span>
          {slot.prob != null && <Pct value={slot.prob} />}
        </>
      ) : (
        <span className="ts-empty">{slot.editable ? 'Pick player…' : slot.placeholder}</span>
      )}
    </>
  )

  if (slot.editable && slot.seedIndex != null) {
    const idx = slot.seedIndex
    return (
      <button
        type="button"
        className={`${cls} ts-edit`}
        onClick={() => onEdit(idx)}
        aria-label={`Seed ${slot.seed}${slot.player ? `: ${slot.player.name}` : ' — pick player'}`}
      >
        {inner}
      </button>
    )
  }
  return <div className={cls}>{inner}</div>
}

function WinnerCard({ slot }: { slot: Slot }) {
  return (
    <div className={`tcard--winner${slot.player ? ' filled' : ''}`}>
      {slot.player ? (
        <>
          <PlayerAvatar player={slot.player} size={52} />
          <div className="tw-name">{slot.player.name}</div>
          <div className="tw-sub">Champion</div>
        </>
      ) : (
        <div className="tw-placeholder">Winner</div>
      )}
    </div>
  )
}
