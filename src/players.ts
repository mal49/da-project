// Player roster + prediction-view helpers.
// Roster ported from the Claude Design handoff (players.js). Ranks/Elo are
// demo figures; the live win-probability comes from the backend model.
import { GENERATED_PLAYERS } from './players.generated'

// The five BWF disciplines. Singles entries are individuals; doubles/mixed
// entries are a PAIR treated as one team (name = 'A / B', with the pair's Elo).
export type Discipline = 'MS' | 'WS' | 'MD' | 'WD' | 'XD'

export type Player = {
  id: string
  name: string
  country: string
  flag: string
  rank: number
  elo: number
  form: number[] // last 5 results, 1 = win, 0 = loss
  hand: 'R' | 'L'
  height: number
  women?: boolean
  // MS/WS/MD/WD/XD. Absent on the hand-authored core roster (all singles) —
  // use disciplineOf() to read it, which falls back to the `women` flag.
  discipline?: Discipline
}

export type MatchContext = {
  tournament: string
  round: Round
}

export type Round = 'R32' | 'R16' | 'QF' | 'SF' | 'Final'

export type KeyFactor = { label: string; value: number; weight: number }

// View model the result card renders. Probabilities/winner/confidence come from
// the model API; sets + keyFactors are derived client-side for the visualization.
export type PredictionView = {
  pA: number
  pB: number
  winner: Player
  sets: [number, number][]
  keyFactors: KeyFactor[]
  confidence: string
  modelUsed: string
}

// The hand-authored core roster (ids here are referenced by MATCHUPS / findPlayer).
const CORE_PLAYERS: Player[] = [
  { id: 'va', name: 'Viktor Axelsen', country: 'DEN', flag: '🇩🇰', rank: 2, elo: 2650, form: [1, 1, 1, 0, 1], hand: 'R', height: 194 },
  { id: 'kv', name: 'Kunlavut Vitidsarn', country: 'THA', flag: '🇹🇭', rank: 1, elo: 2710, form: [1, 1, 1, 1, 0], hand: 'R', height: 175 },
  { id: 'aa', name: 'Anders Antonsen', country: 'DEN', flag: '🇩🇰', rank: 3, elo: 2605, form: [1, 0, 1, 1, 1], hand: 'R', height: 184 },
  { id: 'sy', name: 'Shi Yu Qi', country: 'CHN', flag: '🇨🇳', rank: 4, elo: 2588, form: [1, 1, 0, 1, 1], hand: 'R', height: 187 },
  { id: 'jc', name: 'Jonatan Christie', country: 'INA', flag: '🇮🇩', rank: 5, elo: 2552, form: [0, 1, 1, 1, 1], hand: 'R', height: 178 },
  { id: 'ag', name: 'Anthony Ginting', country: 'INA', flag: '🇮🇩', rank: 6, elo: 2540, form: [1, 0, 1, 0, 1], hand: 'R', height: 171 },
  { id: 'ly', name: 'Loh Kean Yew', country: 'SGP', flag: '🇸🇬', rank: 7, elo: 2498, form: [1, 1, 0, 1, 0], hand: 'R', height: 175 },
  { id: 'lz', name: 'Lee Zii Jia', country: 'MAS', flag: '🇲🇾', rank: 10, elo: 2450, form: [0, 1, 1, 0, 1], hand: 'R', height: 183 },
  { id: 'lc', name: 'Lee Cheuk Yiu', country: 'HKG', flag: '🇭🇰', rank: 9, elo: 2466, form: [1, 0, 0, 1, 1], hand: 'R', height: 178 },
  { id: 'ct', name: 'Chou Tien Chen', country: 'TPE', flag: '🇹🇼', rank: 8, elo: 2478, form: [1, 1, 1, 0, 0], hand: 'R', height: 180 },
  { id: 'kn', name: 'Kodai Naraoka', country: 'JPN', flag: '🇯🇵', rank: 11, elo: 2430, form: [1, 0, 1, 1, 0], hand: 'R', height: 176 },
  { id: 'pp', name: 'Prannoy H. S.', country: 'IND', flag: '🇮🇳', rank: 12, elo: 2415, form: [0, 1, 0, 1, 1], hand: 'R', height: 175 },
  { id: 'll', name: 'Lakshya Sen', country: 'IND', flag: '🇮🇳', rank: 13, elo: 2402, form: [1, 1, 0, 0, 1], hand: 'R', height: 180 },
  { id: 'tp', name: 'Toma Junior Popov', country: 'FRA', flag: '🇫🇷', rank: 14, elo: 2380, form: [0, 1, 1, 1, 0], hand: 'R', height: 186 },
  { id: 'kk', name: 'Kenta Nishimoto', country: 'JPN', flag: '🇯🇵', rank: 15, elo: 2365, form: [1, 0, 1, 0, 1], hand: 'R', height: 175 },
  // Added so the BWF-rankings ladder can show the real top 8 (these three sit in
  // it but had no ingested match history). Elo/height are demo placeholders like
  // the rest of the roster; rank/points shown on the ladder come from /rankings.
  { id: 'cpo', name: 'Christo Popov', country: 'FRA', flag: '🇫🇷', rank: 4, elo: 2520, form: [1, 1, 0, 1, 1], hand: 'R', height: 183 },
  { id: 'lsf', name: 'Li Shi Feng', country: 'CHN', flag: '🇨🇳', rank: 7, elo: 2545, form: [1, 0, 1, 1, 0], hand: 'R', height: 180 },
  { id: 'lcy', name: 'Lin Chun-Yi', country: 'TPE', flag: '🇹🇼', rank: 8, elo: 2495, form: [0, 1, 1, 0, 1], hand: 'R', height: 178 },
  { id: 'as', name: 'An Se-young', country: 'KOR', flag: '🇰🇷', rank: 1, elo: 2720, form: [1, 1, 1, 1, 1], hand: 'R', height: 168, women: true },
  { id: 'cy', name: 'Chen Yu Fei', country: 'CHN', flag: '🇨🇳', rank: 2, elo: 2640, form: [1, 1, 0, 1, 1], hand: 'R', height: 171, women: true },
  { id: 'ay', name: 'Akane Yamaguchi', country: 'JPN', flag: '🇯🇵', rank: 3, elo: 2610, form: [1, 0, 1, 1, 1], hand: 'R', height: 156, women: true },
  { id: 'tt', name: 'Tai Tzu-ying', country: 'TPE', flag: '🇹🇼', rank: 5, elo: 2580, form: [1, 1, 1, 0, 0], hand: 'R', height: 163, women: true },
  { id: 'cm', name: 'Carolina Marín', country: 'ESP', flag: '🇪🇸', rank: 4, elo: 2595, form: [1, 1, 0, 1, 1], hand: 'L', height: 172, women: true },
  { id: 'ps', name: 'P. V. Sindhu', country: 'IND', flag: '🇮🇳', rank: 11, elo: 2440, form: [0, 1, 0, 1, 1], hand: 'R', height: 179, women: true },
  { id: 'hb', name: 'He Bing Jiao', country: 'CHN', flag: '🇨🇳', rank: 6, elo: 2548, form: [1, 0, 1, 1, 0], hand: 'L', height: 169, women: true },
  { id: 'pc', name: 'Pornpawee Chochuwong', country: 'THA', flag: '🇹🇭', rank: 8, elo: 2492, form: [1, 1, 0, 0, 1], hand: 'R', height: 173, women: true },
  // Added so the women's BWF-rankings ladder shows real avatars/Pick metadata for
  // its current top 8. Names match backend/data/bwf_rankings.json exactly so the
  // ladder can join; Elo/height are demo placeholders, rank/points come from /rankings.
  { id: 'wzy', name: 'Wang Zhiyi', country: 'CHN', flag: '🇨🇳', rank: 2, elo: 2618, form: [1, 1, 1, 0, 1], hand: 'R', height: 172, women: true },
  { id: 'hy', name: 'Han Yue', country: 'CHN', flag: '🇨🇳', rank: 5, elo: 2560, form: [1, 0, 1, 1, 0], hand: 'R', height: 170, women: true },
  { id: 'pkw', name: 'Putri Kusuma Wardani', country: 'INA', flag: '🇮🇩', rank: 6, elo: 2530, form: [1, 1, 0, 1, 1], hand: 'R', height: 168, women: true },
  { id: 'ri', name: 'Ratchanok Intanon', country: 'THA', flag: '🇹🇭', rank: 7, elo: 2520, form: [0, 1, 1, 0, 1], hand: 'R', height: 168, women: true },
]

// Full pickable roster: the curated core plus players mined from the real
// tournament CSVs (backend/build_roster.py) so the draw pool runs deep enough
// for the 32-player bracket. Deduped by name, core entries win.
export const PLAYERS: Player[] = [
  ...CORE_PLAYERS,
  ...GENERATED_PLAYERS.filter((g) => !CORE_PLAYERS.some((c) => c.name === g.name)),
]

// Curated sample matchups for the "Try these →" chips.
export const MATCHUPS: [string, string][] = [
  ['va', 'kv'],
  ['lz', 'va'],
  ['as', 'cy'],
  ['cm', 'ay'],
  ['sy', 'aa'],
]

export const ROUNDS: Round[] = ['R32', 'R16', 'QF', 'SF', 'Final']

export function findPlayer(id: string): Player | undefined {
  return PLAYERS.find((p) => p.id === id)
}

// ---- Live leaderboard data (real Elo + record + form from the backend) ----
// The roster above stays the canonical source for hand/height/flag/country
// code; the leaderboard enriches it with these real, match-derived stats.
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export type RealStats = {
  elo: number
  rank: number | null // real world rank (badmintonranks), null if unknown
  wins: number
  losses: number
  played: number
  form: number[] // last 5 results, oldest -> newest, 1 = win
}

export type LeaderboardData = {
  available: boolean
  season: string
  stats: Map<string, RealStats> // keyed by player name
}

type LeaderboardApiResponse = {
  available: boolean
  season: string
  players: (RealStats & { name: string })[]
}

// Fetch /players and index real stats by name. Never throws: on any failure
// (backend offline, no ingested data) returns available:false so callers fall
// back to the static demo roster.
export async function fetchLeaderboard(): Promise<LeaderboardData> {
  try {
    const res = await fetch(`${API_BASE_URL}/players`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = (await res.json()) as LeaderboardApiResponse
    const stats = new Map<string, RealStats>()
    if (data.available) {
      for (const p of data.players) {
        stats.set(p.name, {
          elo: p.elo,
          rank: p.rank ?? null,
          wins: p.wins,
          losses: p.losses,
          played: p.played,
          form: p.form,
        })
      }
    }
    return { available: stats.size > 0, season: data.season ?? '', stats }
  } catch {
    return { available: false, season: '', stats: new Map() }
  }
}

// ---- Official BWF World Rankings (snapshot served by the backend) ----
// Real rank + points from Wikipedia (see backend/fetch_wikipedia_rankings.py),
// enriched with match-derived record/form (null for players we have no history for).
export type RankingEntry = {
  rank: number
  name: string
  country: string // 3-letter nation code
  points: number
  tournaments: number | null
  wins: number | null
  losses: number | null
  form: number[] | null
  elo: number | null
}

// Per-discipline ranking lists. men/women are singles; md/wd/xd are pairs (each
// entry's `name` is 'Player A / Player B').
export type RankingsData = {
  available: boolean
  asOf: string
  source: string
  men: RankingEntry[]
  women: RankingEntry[]
  md: RankingEntry[]
  wd: RankingEntry[]
  xd: RankingEntry[]
}

type RankingsApiResponse = {
  available: boolean
  as_of: string
  source: string
  men: RankingEntry[]
  women: RankingEntry[]
  md?: RankingEntry[]
  wd?: RankingEntry[]
  xd?: RankingEntry[]
}

// Fetch /rankings. Never throws: on failure returns available:false so the
// leaderboard falls back to the static demo roster.
export async function fetchRankings(): Promise<RankingsData> {
  try {
    const res = await fetch(`${API_BASE_URL}/rankings`)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const d = (await res.json()) as RankingsApiResponse
    return {
      available: Boolean(d.available),
      asOf: d.as_of ?? '',
      source: d.source ?? '',
      men: d.men ?? [],
      women: d.women ?? [],
      md: d.md ?? [],
      wd: d.wd ?? [],
      xd: d.xd ?? [],
    }
  } catch {
    return { available: false, asOf: '', source: '', men: [], women: [], md: [], wd: [], xd: [] }
  }
}

// ---- Tournament bracket simulation (POST /simulate) ----
export type BracketMatch = {
  player_a: string
  player_b: string
  prob_a: number
  prob_b: number
  winner: string
}

export type BracketRound = {
  name: string
  size: number
  matches: BracketMatch[]
}

export type TournamentResult = {
  available: boolean
  champion: string
  modelUsed: string
  rounds: BracketRound[]
  error?: string
}

type TournamentApiResponse = {
  champion: string
  model_used: string
  rounds: BracketRound[]
}

export type SeedEntry = { name: string; rank: number; elo: number }

// Run a single-elimination bracket on the backend model. `seeded` is the list of
// entrants already arranged in bracket order (slot 0 vs slot 1, ...). Never
// throws: returns available:false (+ error message) on any failure.
export async function simulateTournament(
  seeded: SeedEntry[],
  matchType: Discipline,
  tournamentName: string,
): Promise<TournamentResult> {
  try {
    const res = await fetch(`${API_BASE_URL}/simulate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        players: seeded.map((s) => ({ name: s.name, rank: s.rank, elo: s.elo })),
        tournament_name: tournamentName,
        match_type: matchType,
      }),
    })
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as { detail?: string } | null
      throw new Error(body?.detail ?? `Request failed with ${res.status}`)
    }
    const d = (await res.json()) as TournamentApiResponse
    return { available: true, champion: d.champion, modelUsed: d.model_used, rounds: d.rounds }
  } catch (e) {
    return {
      available: false,
      champion: '',
      modelUsed: '',
      rounds: [],
      error: e instanceof Error ? e.message : 'Unable to reach the simulator.',
    }
  }
}

// Standard single-elimination seed slotting for a power-of-two draw: returns the
// 1-indexed seed sitting in each bracket slot, so #1 and #2 can only meet in the
// final. e.g. n=8 -> [1,8,4,5,2,7,3,6].
export function seedOrder(n: number): number[] {
  let seeds = [1]
  while (seeds.length < n) {
    const m = seeds.length * 2 + 1
    const next: number[] = []
    for (const s of seeds) next.push(s, m - s)
    seeds = next
  }
  return seeds
}

export function initials(name: string): string {
  return name
    .split(' ')
    .map((s) => s[0])
    .slice(0, 2)
    .join('')
}

export function lastName(name: string): string {
  return name.split(' ').slice(-1)[0]
}

// Display label for the bracket row. For pairs ("A / B"), shows the last name of
// each side ("Yang / Yi") so two distinct pairs aren't collapsed onto the same
// token (e.g. CHN "Ou Xuan Yi" vs TPE "Liu Yi" both truncated to "Yi"). For
// individuals, returns just the last name as before.
export function shortLabel(name: string): string {
  if (!name.includes(' / ')) return lastName(name)
  const sides = name.split(' / ')
  return sides.map((s) => lastName(s)).join(' / ')
}

// Map the design's short round codes to the labels the backend ROUND_MAPPING expects.
export function roundToApi(round: Round): string {
  switch (round) {
    case 'R32':
      return 'Round of 32'
    case 'R16':
      return 'Round of 16'
    case 'QF':
      return 'Quarter final'
    case 'SF':
      return 'Semi final'
    case 'Final':
      return 'Final'
  }
}

// A player's discipline: explicit field if present (doubles/mixed pairs and
// generated singles carry it), else inferred from the legacy `women` flag for the
// hand-authored core roster (all singles).
export function disciplineOf(p: Player): Discipline {
  return p.discipline ?? (p.women ? 'WS' : 'MS')
}

// Discipline for a head-to-head prediction: take it from side A (both sides
// should be the same discipline — the UI lets you pick, like the singles flow).
export function matchTypeFor(a: Player): Discipline {
  return disciplineOf(a)
}

// Derive the projected scoreline + ranked key factors that the result card shows.
// `pA` is the model's win probability for player A. The key factors are the model's
// two real per-player features — Elo gap and world-rank gap — taken from the actual
// match-derived ratings (not the demo roster), so the card can't contradict itself.
export function buildPredictionView(
  a: Player,
  b: Player,
  pA: number,
  confidence: string,
  modelUsed: string,
  realEloA: number | null = null,
  realEloB: number | null = null,
  realRankA: number | null = null,
  realRankB: number | null = null,
): PredictionView {
  const pB = 1 - pA
  const winner = pA >= 0.5 ? a : b
  const conf = Math.max(pA, pB)

  // Projected scoreline (visualization), scaled by model confidence.
  const sets: [number, number][] = []
  const threeSets = conf < 0.68
  if (threeSets) {
    sets.push([21, 14 + Math.floor((1 - conf) * 8)])
    sets.push([18 + Math.floor((1 - conf) * 4), 21])
    sets.push([21, 13 + Math.floor((1 - conf) * 9)])
  } else {
    sets.push([21, 14 + Math.floor((1 - conf) * 8)])
    sets.push([21, 15 + Math.floor((1 - conf) * 7)])
  }

  // Both diffs are A-minus-B and positive => favours A (lower rank number = better).
  // 0 when a player is unrated, so nothing fabricated is shown.
  const eloDiff = realEloA != null && realEloB != null ? realEloA - realEloB : 0
  const rankDiff = realRankA != null && realRankB != null ? realRankB - realRankA : 0

  const keyFactors: KeyFactor[] = [
    { label: 'Elo gap', value: eloDiff, weight: Math.abs(eloDiff) },
    { label: 'World rank', value: rankDiff, weight: Math.abs(rankDiff) * 12 },
  ].sort((x, y) => y.weight - x.weight)

  return { pA, pB, winner, sets, keyFactors, confidence, modelUsed }
}
