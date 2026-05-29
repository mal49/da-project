import { useMemo, useState } from 'react'
import type { Player } from '../players'
import { PLAYERS } from '../players'
import { PlayerAvatar } from './PlayerAvatar'

type Props = {
  onPickPlayer: (player: Player) => void
}

export function Leaderboard({ onPickPlayer }: Props) {
  const [div, setDiv] = useState<'men' | 'women'>('men')

  const list = useMemo(
    () =>
      PLAYERS.filter((p) => (div === 'women' ? p.women : !p.women))
        .sort((a, b) => a.rank - b.rank)
        .slice(0, 8),
    [div],
  )

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
          <span>ELO</span>
          <span>2026 Record</span>
          <span>Last 5</span>
          <span />
        </div>
        {list.map((p, idx) => {
          const wins = p.form.reduce((s, x) => s + x, 0)
          return (
            <div className={`lb-row lb-rank-${idx + 1}`} key={p.id}>
              <span className="lb-rank">#{p.rank}</span>
              <span className="lb-name">
                <PlayerAvatar player={p} size={36} />
                <span>
                  <span>{p.name}</span>
                  <span className="country">
                    {p.country} · {p.hand}-HAND
                  </span>
                </span>
              </span>
              <span className="lb-elo">{p.elo}</span>
              <span className="lb-rec">
                <strong>{18 + wins * 3}</strong>–{9 - wins}
              </span>
              <span className="lb-form">
                {p.form.map((r, i) => (
                  <span key={i} className={`dot ${r ? 'w' : 'l'}`}>
                    {r ? 'W' : 'L'}
                  </span>
                ))}
              </span>
              <button className="lb-pick" onClick={() => onPickPlayer(p)}>
                Pick →
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
