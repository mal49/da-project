import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { Player } from '../players'
import { PLAYERS } from '../players'
import { PlayerAvatar } from './PlayerAvatar'

type Props = {
  open: boolean
  title: string
  excludeId?: string
  onPick: (player: Player) => void
  onClose: () => void
}

type Group = { label: string | null; items: Player[] }

export function PlayerModal({ open, title, excludeId, onPick, onClose }: Props) {
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setQ('')
      setSelected(0)
      const id = setTimeout(() => inputRef.current?.focus(), 50)
      return () => clearTimeout(id)
    }
  }, [open])

  const filtered = useMemo(() => {
    const list = PLAYERS.filter((p) => p.id !== excludeId)
    if (!q.trim()) return list
    const needle = q.toLowerCase()
    return list.filter(
      (p) =>
        p.name.toLowerCase().includes(needle) ||
        p.country.toLowerCase().includes(needle),
    )
  }, [q, excludeId])

  // Group by men/women only when not searching.
  const grouped = useMemo<Group[]>(() => {
    if (q.trim()) return [{ label: null, items: filtered }]
    const byRank = (a: Player, b: Player) => a.rank - b.rank
    return [
      { label: "Men's Singles", items: filtered.filter((p) => !p.women).sort(byRank) },
      { label: "Women's Singles", items: filtered.filter((p) => p.women).sort(byRank) },
    ]
  }, [filtered, q])

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
                        <span>
                          {p.country} · {p.hand}-hand · {p.height}cm
                        </span>
                      </div>
                      <div className="mright">
                        <span className="mrank">#{p.rank}</span>
                        <span className="melo">{p.elo} ELO</span>
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
