// Player roster + prediction-view helpers.
// Roster ported from the Claude Design handoff (players.js). Ranks/Elo are
// demo figures; the live win-probability comes from the backend model.

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
}

export type MatchContext = {
  tournament: string
  round: Round
  surface: Surface
  bestOf: 3 | 5
}

export type Round = 'R32' | 'R16' | 'QF' | 'SF' | 'Final'
export type Surface = 'Mat' | 'Wood' | 'Cement'

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

export const PLAYERS: Player[] = [
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
  { id: 'as', name: 'An Se-young', country: 'KOR', flag: '🇰🇷', rank: 1, elo: 2720, form: [1, 1, 1, 1, 1], hand: 'R', height: 168, women: true },
  { id: 'cy', name: 'Chen Yu Fei', country: 'CHN', flag: '🇨🇳', rank: 2, elo: 2640, form: [1, 1, 0, 1, 1], hand: 'R', height: 171, women: true },
  { id: 'ay', name: 'Akane Yamaguchi', country: 'JPN', flag: '🇯🇵', rank: 3, elo: 2610, form: [1, 0, 1, 1, 1], hand: 'R', height: 156, women: true },
  { id: 'tt', name: 'Tai Tzu-ying', country: 'TPE', flag: '🇹🇼', rank: 5, elo: 2580, form: [1, 1, 1, 0, 0], hand: 'R', height: 163, women: true },
  { id: 'cm', name: 'Carolina Marín', country: 'ESP', flag: '🇪🇸', rank: 4, elo: 2595, form: [1, 1, 0, 1, 1], hand: 'L', height: 172, women: true },
  { id: 'ps', name: 'P. V. Sindhu', country: 'IND', flag: '🇮🇳', rank: 11, elo: 2440, form: [0, 1, 0, 1, 1], hand: 'R', height: 179, women: true },
  { id: 'hb', name: 'He Bing Jiao', country: 'CHN', flag: '🇨🇳', rank: 6, elo: 2548, form: [1, 0, 1, 1, 0], hand: 'L', height: 169, women: true },
  { id: 'pc', name: 'Pornpawee Chochuwong', country: 'THA', flag: '🇹🇭', rank: 8, elo: 2492, form: [1, 1, 0, 0, 1], hand: 'R', height: 173, women: true },
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
export const SURFACES: Surface[] = ['Mat', 'Wood', 'Cement']

export function findPlayer(id: string): Player | undefined {
  return PLAYERS.find((p) => p.id === id)
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

const formScore = (p: Player) => p.form.reduce((sum, x) => sum + x, 0)

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

// Singles only in this UI: infer division from player A.
export function matchTypeFor(a: Player): 'MS' | 'WS' {
  return a.women ? 'WS' : 'MS'
}

// Derive the projected scoreline + ranked key factors that the result card shows.
// `pA` is the model's win probability for player A.
export function buildPredictionView(
  a: Player,
  b: Player,
  ctx: MatchContext,
  pA: number,
  confidence: string,
  modelUsed: string,
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

  // Key factors derived from the real player stats + chosen context.
  const eloDiff = a.elo - b.elo
  const rankAdv = (b.rank - a.rank) * 8
  const formAdv = (formScore(a) - formScore(b)) * 14
  let ctxAdj = 0
  if (ctx.round === 'Final') ctxAdj += eloDiff > 0 ? 12 : -12
  if (ctx.surface === 'Wood') ctxAdj += a.hand === 'L' ? -4 : 2

  const keyFactors: KeyFactor[] = [
    { label: 'Elo gap', value: eloDiff, weight: Math.abs(eloDiff) / 5 },
    { label: 'Recent form', value: formAdv, weight: Math.abs(formAdv) },
    { label: 'World rank', value: rankAdv, weight: Math.abs(rankAdv) },
    { label: 'Match context', value: ctxAdj, weight: Math.abs(ctxAdj) },
  ].sort((x, y) => y.weight - x.weight)

  return { pA, pB, winner, sets, keyFactors, confidence, modelUsed }
}
