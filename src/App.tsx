import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import heroImg from './assets/hero.png'
import './App.css'

type PredictionRequest = {
  player_a_name: string
  player_b_name: string
  player_a_rank: number
  player_b_rank: number
  player_a_elo?: number
  player_b_elo?: number
  tournament_name: string
  round: string
  match_type: string
}

type PredictionResponse = {
  player_a_win_probability: number
  player_b_win_probability: number
  predicted_winner: string
  confidence: string
  model_used: string
}

type FormState = {
  playerAName: string
  playerAPartnerName: string
  playerBName: string
  playerBPartnerName: string
  playerARank: string
  playerBRank: string
  playerAElo: string
  playerBElo: string
  tournamentName: string
  round: string
  matchType: string
}

type Player = {
  name: string
  rank: number
  elo: number
  categories: string[]
}

const apiBaseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const playerSourceUrl = 'https://badmintonranks.com/'

const playerDirectory: Player[] = [
  { name: 'Lee Zii Jia', rank: 10, elo: 2450, categories: ['MS'] },
  { name: 'Viktor Axelsen', rank: 2, elo: 2650, categories: ['MS'] },
  { name: 'Kunlavut Vitidsarn', rank: 4, elo: 2580, categories: ['MS'] },
  { name: 'Shi Yu Qi', rank: 1, elo: 2680, categories: ['MS'] },
  { name: 'Anders Antonsen', rank: 3, elo: 2600, categories: ['MS'] },
  { name: 'Kodai Naraoka', rank: 6, elo: 2520, categories: ['MS'] },
  { name: 'Anthony Sinisuka Ginting', rank: 8, elo: 2485, categories: ['MS'] },
  { name: 'Loh Kean Yew', rank: 13, elo: 2410, categories: ['MS'] },
  { name: 'Jonatan Christie', rank: 5, elo: 2545, categories: ['MS'] },
  { name: 'Li Shi Feng', rank: 7, elo: 2505, categories: ['MS'] },
  { name: 'Ng Tze Yong', rank: 18, elo: 2350, categories: ['MS'] },
  { name: 'An Se Young', rank: 1, elo: 2700, categories: ['WS'] },
  { name: 'Chen Yu Fei', rank: 2, elo: 2640, categories: ['WS'] },
  { name: 'Akane Yamaguchi', rank: 4, elo: 2590, categories: ['WS'] },
  { name: 'Tai Tzu Ying', rank: 5, elo: 2550, categories: ['WS'] },
  { name: 'Carolina Marin', rank: 6, elo: 2525, categories: ['WS'] },
  { name: 'P. V. Sindhu', rank: 12, elo: 2425, categories: ['WS'] },
  { name: 'Gregoria Mariska Tunjung', rank: 7, elo: 2495, categories: ['WS'] },
  { name: 'Han Yue', rank: 8, elo: 2475, categories: ['WS'] },
  { name: 'Goh Jin Wei', rank: 30, elo: 2240, categories: ['WS'] },
  { name: 'Aaron Chia', rank: 5, elo: 2520, categories: ['MD', 'XD'] },
  { name: 'Soh Wooi Yik', rank: 5, elo: 2520, categories: ['MD'] },
  { name: 'Satwiksairaj Rankireddy', rank: 3, elo: 2580, categories: ['MD'] },
  { name: 'Chirag Shetty', rank: 3, elo: 2580, categories: ['MD'] },
  { name: 'Fajar Alfian', rank: 7, elo: 2490, categories: ['MD'] },
  { name: 'Muhammad Rian Ardianto', rank: 7, elo: 2490, categories: ['MD'] },
  { name: 'Kang Min Hyuk', rank: 6, elo: 2505, categories: ['MD'] },
  { name: 'Seo Seung Jae', rank: 6, elo: 2505, categories: ['MD', 'XD'] },
  { name: 'Kim Astrup', rank: 8, elo: 2470, categories: ['MD'] },
  { name: 'Anders Skaarup Rasmussen', rank: 8, elo: 2470, categories: ['MD'] },
  { name: 'Chen Qing Chen', rank: 1, elo: 2670, categories: ['WD'] },
  { name: 'Jia Yi Fan', rank: 1, elo: 2670, categories: ['WD'] },
  { name: 'Pearly Tan', rank: 8, elo: 2475, categories: ['WD', 'XD'] },
  { name: 'Thinaah Muralitharan', rank: 8, elo: 2475, categories: ['WD'] },
  { name: 'Baek Ha Na', rank: 2, elo: 2630, categories: ['WD'] },
  { name: 'Lee So Hee', rank: 2, elo: 2630, categories: ['WD'] },
  { name: 'Nami Matsuyama', rank: 5, elo: 2540, categories: ['WD'] },
  { name: 'Chiharu Shida', rank: 5, elo: 2540, categories: ['WD'] },
  { name: 'Huang Dong Ping', rank: 2, elo: 2635, categories: ['XD', 'WD'] },
  { name: 'Feng Yan Zhe', rank: 2, elo: 2635, categories: ['XD'] },
  { name: 'Zheng Si Wei', rank: 1, elo: 2680, categories: ['XD'] },
  { name: 'Huang Ya Qiong', rank: 1, elo: 2680, categories: ['XD'] },
  { name: 'Goh Soon Huat', rank: 9, elo: 2465, categories: ['XD'] },
  { name: 'Shevon Jemie Lai', rank: 9, elo: 2465, categories: ['XD'] },
]

const rounds = [
  'Qualification',
  'Round 1',
  'Round 2',
  'Round 3',
  'Round of 32',
  'Round of 16',
  'Quarter final',
  'Semi final',
  'Final',
]

const matchTypes = [
  { label: 'Men Singles', value: 'MS' },
  { label: 'Women Singles', value: 'WS' },
  { label: 'Men Doubles', value: 'MD' },
  { label: 'Women Doubles', value: 'WD' },
  { label: 'Mixed Doubles', value: 'XD' },
]

const initialForm: FormState = {
  playerAName: 'Lee Zii Jia',
  playerAPartnerName: '',
  playerBName: 'Viktor Axelsen',
  playerBPartnerName: '',
  playerARank: '10',
  playerBRank: '2',
  playerAElo: '2450',
  playerBElo: '2650',
  tournamentName: '',
  round: '',
  matchType: '',
}

function optionalNumber(value: string) {
  return value.trim() ? Number(value) : undefined
}

function toPercent(value: number) {
  return `${Math.round(value * 100)}%`
}

function isDoublesMatch(matchType: string) {
  return ['MD', 'WD', 'XD'].includes(matchType)
}

function formatSideName(primary: string, partner: string, fallback: string) {
  const names = [primary, partner].map((name) => name.trim()).filter(Boolean)
  return names.length ? names.join(' / ') : fallback
}

function findPlayer(name: string) {
  const normalizedName = name.trim().toLowerCase()
  return playerDirectory.find(
    (player) => player.name.toLowerCase() === normalizedName,
  )
}

function getSuggestedPlayers(matchType: string) {
  if (!matchType) {
    return playerDirectory
  }

  return playerDirectory.filter((player) =>
    player.categories.includes(matchType),
  )
}

function getSideMetrics(names: string[]) {
  const players = names.map(findPlayer)

  if (players.some((player) => !player)) {
    return null
  }

  const knownPlayers = players as Player[]
  const rank = Math.round(
    knownPlayers.reduce((total, player) => total + player.rank, 0) /
      knownPlayers.length,
  )
  const elo = Math.round(
    knownPlayers.reduce((total, player) => total + player.elo, 0) /
      knownPlayers.length,
  )

  return { rank, elo }
}

function App() {
  const [form, setForm] = useState<FormState>(initialForm)
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const showDoublesFields = isDoublesMatch(form.matchType)
  const sideAName = showDoublesFields
    ? formatSideName(form.playerAName, form.playerAPartnerName, 'Side A')
    : form.playerAName || 'Player A'
  const sideBName = showDoublesFields
    ? formatSideName(form.playerBName, form.playerBPartnerName, 'Side B')
    : form.playerBName || 'Player B'
  const suggestedPlayers = getSuggestedPlayers(form.matchType)
  const sideAMetrics = getSideMetrics(
    showDoublesFields
      ? [form.playerAName, form.playerAPartnerName]
      : [form.playerAName],
  )
  const sideBMetrics = getSideMetrics(
    showDoublesFields
      ? [form.playerBName, form.playerBPartnerName]
      : [form.playerBName],
  )
  const playersReady = Boolean(sideAMetrics && sideBMetrics)

  const resultRows = useMemo(() => {
    if (!prediction) {
      return []
    }

    return [
      {
        name: sideAName,
        value: prediction.player_a_win_probability,
      },
      {
        name: sideBName,
        value: prediction.player_b_win_probability,
      },
    ]
  }, [prediction, sideAName, sideBName])

  function updateField(field: keyof FormState, value: string) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setPrediction(null)
    setIsLoading(true)

    const payload: PredictionRequest = {
      player_a_name: sideAName,
      player_b_name: sideBName,
      player_a_rank: sideAMetrics?.rank ?? Number(form.playerARank),
      player_b_rank: sideBMetrics?.rank ?? Number(form.playerBRank),
      player_a_elo: sideAMetrics?.elo ?? optionalNumber(form.playerAElo),
      player_b_elo: sideBMetrics?.elo ?? optionalNumber(form.playerBElo),
      tournament_name: form.tournamentName.trim() || 'Unknown tournament',
      round: form.round || 'Round 2',
      match_type: form.matchType || 'MS',
    }

    try {
      const response = await fetch(`${apiBaseUrl}/predict`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail ?? `Request failed with ${response.status}`)
      }

      const data = (await response.json()) as PredictionResponse
      setPrediction(data)
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'Unable to get prediction.'
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="scoreboard" aria-labelledby="page-title">
        <div className="scoreboard-copy">
          <div className="eyebrow">
            <img src={heroImg} alt="" />
            Badminton AI Predictor
          </div>
          <h1 id="page-title">
            Match<br />
            <span>Predictor</span>
          </h1>
          <p>
            Select two players and get an AI-powered probability estimate for
            who wins. Add match context for sharper predictions.
          </p>
        </div>

        <div className="status-strip" aria-label="API endpoint">
          <span>API</span>
          <code>{apiBaseUrl}/predict</code>
        </div>
      </section>

      <section className="workspace">
        <form className="predictor-form" onSubmit={handleSubmit}>
          <div className="form-section">
            <div className="section-heading">
              <h2>Players</h2>
              <a href={playerSourceUrl} target="_blank" rel="noreferrer">
                BadmintonRanks
              </a>
            </div>
            <datalist id="player-options">
              {suggestedPlayers.map((player) => (
                <option key={player.name} value={player.name} />
              ))}
            </datalist>
            <div className="field-grid two-columns">
              <label>
                {showDoublesFields ? 'Side A player 1' : 'Player A'}
                <input
                  list="player-options"
                  placeholder="Search player name"
                  required
                  value={form.playerAName}
                  onChange={(event) =>
                    updateField('playerAName', event.target.value)
                  }
                />
              </label>
              <label>
                {showDoublesFields ? 'Side B player 1' : 'Player B'}
                <input
                  list="player-options"
                  placeholder="Search player name"
                  required
                  value={form.playerBName}
                  onChange={(event) =>
                    updateField('playerBName', event.target.value)
                  }
                />
              </label>
              {showDoublesFields && (
                <>
                  <label>
                    Side A player 2
                    <input
                      list="player-options"
                      placeholder="Search partner name"
                      required
                      value={form.playerAPartnerName}
                      onChange={(event) =>
                        updateField('playerAPartnerName', event.target.value)
                      }
                    />
                  </label>
                  <label>
                    Side B player 2
                    <input
                      list="player-options"
                      placeholder="Search partner name"
                      required
                      value={form.playerBPartnerName}
                      onChange={(event) =>
                        updateField('playerBPartnerName', event.target.value)
                      }
                    />
                  </label>
                </>
              )}
              <label>
                {showDoublesFields ? 'Side A rank' : 'Player A rank'}
                <input
                  required
                  min="1"
                  max="500"
                  readOnly
                  type="number"
                  value={sideAMetrics?.rank ?? ''}
                />
              </label>
              <label>
                {showDoublesFields ? 'Side B rank' : 'Player B rank'}
                <input
                  required
                  min="1"
                  max="500"
                  readOnly
                  type="number"
                  value={sideBMetrics?.rank ?? ''}
                />
              </label>
              <label>
                {showDoublesFields ? 'Side A Elo' : 'Player A Elo'}
                <input
                  min="1000"
                  max="3500"
                  placeholder="Optional"
                  readOnly
                  type="number"
                  value={sideAMetrics?.elo ?? ''}
                />
              </label>
              <label>
                {showDoublesFields ? 'Side B Elo' : 'Player B Elo'}
                <input
                  min="1000"
                  max="3500"
                  placeholder="Optional"
                  readOnly
                  type="number"
                  value={sideBMetrics?.elo ?? ''}
                />
              </label>
            </div>
            <p className="field-note">
              Search and choose players from the suggestions. Rank and Elo are
              filled from the selected {showDoublesFields ? 'side.' : 'player.'}
            </p>
            {!playersReady && (
              <p className="field-note warning-note">
                Select valid suggested names for both sides before predicting.
              </p>
            )}
          </div>

          <div className="form-section">
            <h2>Match</h2>
            <div className="field-grid">
              <label>
                Tournament
                <input
                  placeholder="Optional"
                  value={form.tournamentName}
                  onChange={(event) =>
                    updateField('tournamentName', event.target.value)
                  }
                />
              </label>
              <label>
                Round
                <select
                  value={form.round}
                  onChange={(event) => updateField('round', event.target.value)}
                >
                  <option value="">Optional</option>
                  {rounds.map((round) => (
                    <option key={round} value={round}>
                      {round}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Match type
                <select
                  value={form.matchType}
                  onChange={(event) =>
                    updateField('matchType', event.target.value)
                  }
                >
                  <option value="">Optional</option>
                  {matchTypes.map((matchType) => (
                    <option key={matchType.value} value={matchType.value}>
                      {matchType.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <p className="field-note">
              These fields can be left blank. The prediction will still run
              using default match context.
            </p>
          </div>

          <button
            className="submit-button"
            disabled={isLoading || !playersReady}
          >
            {isLoading ? 'Predicting...' : 'Predict winner'}
          </button>
        </form>

        <aside className={`result-panel${prediction ? ' has-prediction' : ''}`} aria-live="polite">
          <div>
            <p className="panel-label">🏆 Predicted Winner</p>
            <h2>{prediction?.predicted_winner ?? 'Awaiting Match'}</h2>
            <p className="panel-copy">
              {prediction
                ? `${prediction.confidence} confidence · ${prediction.model_used}`
                : 'Fill in the match details and hit Predict to see the AI forecast.'}
            </p>
          </div>

          {error && <p className="error-message">{error}</p>}

          {prediction ? (
            <div className="probabilities">
              {resultRows.map((row) => (
                <div className="probability-row" key={row.name}>
                  <div className="probability-header">
                    <span>{row.name}</span>
                    <strong>{toPercent(row.value)}</strong>
                  </div>
                  <div className="meter" aria-hidden="true">
                    <span style={{ width: toPercent(row.value) }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-court" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          )}
        </aside>
      </section>
    </main>
  )
}

export default App
