import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { Discipline, Player } from '../players'
import { PLAYERS, disciplineOf } from '../players'
import { PlayerAvatar } from './PlayerAvatar'

type Props = {
  open: boolean
  title: string
  excludeId?: string
  // When set, the capsule filter opens on this discipline (e.g. the simulator
  // seeding a doubles draw). Omitted in the head-to-head picker -> opens on "All".
  discipline?: Discipline
  eloFor: (name: string) => number | null
  rankFor: (name: string) => number | null
  onPick: (player: Player) => void
  onClose: () => void
}

type Group = { label: string | null; items: Player[] }

// Capsule filter categories: All + the five BWF disciplines. Doubles/mixed
// entries are pairs-as-teams (name = 'A / B') carrying the pair's real rating.
type Category = 'all' | Discipline
const DISCIPLINE_LABEL: Record<Discipline, string> = {
  MS: "Men's Singles",
  WS: "Women's Singles",
  MD: "Men's Doubles",
  WD: "Women's Doubles",
  XD: 'Mixed Doubles',
}
const DISCIPLINE_ORDER: Discipline[] = ['MS', 'WS', 'MD', 'WD', 'XD']
const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'all', label: 'All' },
  ...DISCIPLINE_ORDER.map((d) => ({ key: d as Category, label: DISCIPLINE_LABEL[d] })),
]
const isPair = (d: Discipline): boolean => d === 'MD' || d === 'WD' || d === 'XD'

export function PlayerModal({
  open,
  title,
  excludeId,
  discipline,
  eloFor,
  rankFor,
  onPick,
  onClose,
}: Props) {
  const [q, setQ] = useState('')
  const [category, setCategory] = useState<Category>(discipline ?? 'all')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQ('')
      setCategory(discipline ?? 'all')
      setSelected(0)
      const id = setTimeout(() => inputRef.current?.focus(), 50)
      return () => clearTimeout(id)
    }
  }, [open, discipline])

  const filtered = useMemo(() => {
    let list = PLAYERS.filter((p) => p.id !== excludeId)
    if (category !== 'all') list = list.filter((p) => disciplineOf(p) === category)
    if (q.trim()) {
      const needle = q.toLowerCase()
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(needle) ||
          p.country.toLowerCase().includes(needle),
      )
    }
    return list
  }, [q, excludeId, category])

  // Split into per-discipline groups only on "All" (no search); otherwise the
  // capsule already names the category, so show one flat, rank-sorted list.
  // Order by displayed (real) rank, falling back to the roster rank.
  const grouped = useMemo<Group[]>(() => {
    const byRank = (a: Player, b: Player) =>
      (rankFor(a.name) ?? a.rank) - (rankFor(b.name) ?? b.rank)
    if (category !== 'all' || q.trim()) {
      return [{ label: null, items: [...filtered].sort(byRank) }]
    }
    return DISCIPLINE_ORDER.map((d) => ({
      label: DISCIPLINE_LABEL[d],
      items: filtered.filter((p) => disciplineOf(p) === d).sort(byRank),
    })).filter((g) => g.items.length > 0)
  }, [filtered, q, category, rankFor])

  const flat = useMemo(() => grouped.flatMap((g) => g.items), [grouped])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return
      }
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelected((s) => Math.min(s + 1, flat.length - 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelected((s) => Math.max(s - 1, 0))
      }
      if (e.key === 'Enter' && flat[selected]) {
        e.preventDefault()
        onPick(flat[selected])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, flat, selected, onPick, onClose])

  if (!open) return null

  let runningIdx = -1

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-search-icon">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </div>
          <input
            ref={inputRef}
            className="modal-search"
            placeholder={title || 'Search players by name or country…'}
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setSelected(0)
            }}
          />
          <span className="modal-kbd">ESC</span>
        </div>
        <div className="modal-filters">
          <div className="tabs" role="tablist" aria-label="Category">
            {CATEGORIES.map((c) => (
              <button
                key={c.key}
                className="tab"
                role="tab"
                aria-selected={category === c.key}
                onClick={() => {
                  setCategory(c.key)
                  setSelected(0)
                }}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <div className="modal-list">
          {flat.length === 0 ? (
            <div className="modal-empty">No players match "{q}"</div>
          ) : (
            grouped.map((g, gi) => (
              <Fragment key={gi}>
                {g.label && g.items.length > 0 && (
                  <div className="modal-section">{g.label}</div>
                )}
                {g.items.map((p) => {
                  runningIdx++
                  const idx = runningIdx
                  return (
                    <div
                      key={p.id}
                      className="modal-item"
                      aria-selected={idx === selected}
                      onMouseEnter={() => setSelected(idx)}
                      onClick={() => onPick(p)}
                    >
                      <PlayerAvatar player={p} size={40} />
                      <div className="mname">
                        <b>{p.name}</b>
                        {(() => {
                          const d = disciplineOf(p)
                          return isPair(d) ? (
                            <span>
                              {DISCIPLINE_LABEL[d]}
                              {p.country ? ` · ${p.country}` : ''}
                            </span>
                          ) : (
                            <span>
                              {p.country} · {p.hand}-hand · {p.height}cm
                            </span>
                          )
                        })()}
                      </div>
                      <div className="mright">
                        <span className="mrank">#{rankFor(p.name) ?? p.rank}</span>
                        <span className="melo">
                          {(() => {
                            const e = eloFor(p.name)
                            return e != null ? `${e} ELO` : 'Unrated'
                          })()}
                        </span>
                      </div>
                    </div>
                  )
                })}
              </Fragment>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
