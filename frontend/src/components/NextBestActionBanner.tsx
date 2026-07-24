import type { MouseEvent } from 'react'
import type { NextBestAction } from '../api'
import './NextBestActionBanner.css'

interface Props {
  actions: NextBestAction[]
  aiPowered: boolean
  funnelStage: string
  onActionClick: (label: string, event: MouseEvent<HTMLButtonElement>) => void
}

export default function NextBestActionBanner({
  actions,
  aiPowered,
  funnelStage,
  onActionClick,
}: Props) {
  if (actions.length === 0) return null

  return (
    <div className="nba-banner">
      <div className="nba-header">
        <span className="nba-title">Next Best Action</span>
        <span className="nba-stage">{funnelStage}</span>
        {aiPowered && <span className="nba-ai">AI</span>}
      </div>
      <div className="nba-actions">
        {actions.map((a) => (
          <button
            key={a.action}
            className="nba-chip"
            onClick={(event) => onActionClick(a.label, event)}
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  )
}
