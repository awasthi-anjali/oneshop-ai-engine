import './OmnichannelSyncBanner.css'

interface Props {
  message: string
  channelsUsed?: string[]
  currentChannel: 'oneshop' | 'oneapp'
}

export default function OmnichannelSyncBanner({ message, channelsUsed, currentChannel }: Props) {
  if (!message) return null

  return (
    <div className="omni-sync-banner">
      <span className="omni-sync-icon">⟳</span>
      <div className="omni-sync-text">
        <strong>Omnichannel sync</strong>
        <p>{message}</p>
        {channelsUsed && channelsUsed.length > 1 && (
          <div className="omni-channels">
            {channelsUsed.map((ch) => (
              <span
                key={ch}
                className={`omni-ch-tag ${ch === currentChannel ? 'active' : ''}`}
              >
                {ch === 'oneshop' ? 'OneShop Web' : 'OneApp Mobile'}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
