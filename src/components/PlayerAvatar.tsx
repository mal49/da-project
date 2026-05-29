import type { Player } from '../players'
import { initials } from '../players'

type Props = {
  player: Player
  size?: number
}

export function PlayerAvatar({ player, size = 40 }: Props) {
  return (
    <div
      className="pavatar"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.32,
        borderRadius: size * 0.25,
      }}
    >
      {initials(player.name)}
      <span className="flag">{player.flag}</span>
    </div>
  )
}
