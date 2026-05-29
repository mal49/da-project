import { useEffect, useState } from 'react'
import type { Player, PredictionView } from '../players'
import { lastName } from '../players'

type Props = {
  result: PredictionView
  a: Player
  b: Player
}

export function ResultCard({ result, a, b }: Props) {
  // Start at 50% on mount, then animate to the model's probability via the
  // CSS width transition. (ResultCard remounts on each new prediction.)
  const [animPct, setAnimPct] = useState(50)

  useEffect(() => {
    const id = requestAnimationFrame(() => setAnimPct(result.pA * 100))
    return () => cancelAnimationFrame(id)
  }, [result.pA])

  const { winner } = result
  const isAWinner = winner.id === a.id
  const conf = Math.round(Math.max(result.pA, result.pB) * 100)

  return (
    <div className="result-card">
      <div className="result-head">
        <div>
          <div className="result-tag">
            AI Forecast · {result.confidence.toLowerCase()} confidence
          </div>
          <div className="winner-name">
            <span>{winner.name}</span> {winner.flag} wins in {result.sets.length} sets
          </div>
        </div>
        <div className="conf-pill">{conf}</div>
      </div>

      <div className="pbar-labels">
        <span className="pl">
          <strong>{a.name}</strong>
        </span>
        <span className="pl" style={{ textAlign: 'right' }}>
          <strong>{b.name}</strong>
        </span>
      </div>
      <div className="pbar">
        <div className="fill-a" style={{ width: `${animPct}%` }} />
      </div>
      <div className="pbar-labels">
        <span className="pa">{Math.round(result.pA * 100)}%</span>
        <span className="pb">{Math.round(result.pB * 100)}%</span>
      </div>

      <div className="result-grid">
        <div className="scoreline">
          <div className="h">Projected Scoreline</div>
          <div className="sets">
            {result.sets.map((s, i) => {
              const aWon = s[0] > s[1]
              return (
                <div key={i} className="set-tile">
                  <span className={`a ${aWon ? '' : 'lose'}`}>{s[0]}</span>
                  <span className="dash">—</span>
                  <span className={`b ${aWon ? 'lose' : ''}`}>{s[1]}</span>
                  <span className="label">Set {i + 1}</span>
                </div>
              )
            })}
          </div>
          <div className="result-desc">
            Win probability from <strong>{result.modelUsed}</strong>. Projected
            scoreline is an illustrative best-guess; the model itself weighs Elo,
            rank, recent form, and match context.
          </div>
        </div>

        <div className="factors">
          <div className="h">
            ✦ Why? Key factors favouring{' '}
            {isAWinner ? lastName(a.name) : lastName(b.name)}
          </div>
          {result.keyFactors.map((f, i) => {
            const max = result.keyFactors[0].weight || 1
            const pct = Math.min(100, (f.weight / max) * 100)
            const positive =
              (isAWinner && f.value > 0) || (!isAWinner && f.value < 0)
            return (
              <div key={i} className={`factor ${positive ? '' : 'neg'}`}>
                <span className="fname">{f.label}</span>
                <span className="ftrack">
                  <span className="ffill" style={{ width: `${pct}%` }} />
                </span>
                <span className="fval">
                  {f.value > 0 ? '+' : ''}
                  {Math.round(f.value)}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
