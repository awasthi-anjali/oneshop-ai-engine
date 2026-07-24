import { useCallback, useEffect, useState } from 'react'
import {
  getContinueUrl,
  getOmnichannelContext,
  getStoredSessionId,
  linkCustomer,
  type Channel,
  type OmnichannelContext,
} from '../api'
import './OmnichannelPanel.css'

interface Props {
  channel: Channel
}

export default function OmnichannelPanel({ channel }: Props) {
  const [ctx, setCtx] = useState<OmnichannelContext | null>(null)
  const [customerId, setCustomerId] = useState('demo-customer')
  const [copied, setCopied] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getOmnichannelContext(getStoredSessionId(), channel)
      setCtx(data)
    } finally {
      setLoading(false)
    }
  }, [channel])

  useEffect(() => {
    refresh()
  }, [refresh])

  const copyLink = async (url: string, label: string) => {
    await navigator.clipboard.writeText(url)
    setCopied(label)
    setTimeout(() => setCopied(null), 2000)
  }

  const handleLink = async () => {
    await linkCustomer(customerId.trim(), getStoredSessionId())
    await refresh()
  }

  const openOther = async () => {
    const target: Channel = channel === 'oneshop' ? 'oneapp' : 'oneshop'
    const data = await getContinueUrl(getStoredSessionId(), target)
    window.open(data.continue_url, '_blank')
  }

  if (loading) return <p className="omni-loading">Loading sync status…</p>

  return (
    <div className="omni-panel">
      <h3>Cross-channel sync</h3>
      <p className="omni-desc">
        One shared session powers OneShop (Web) and OneApp (Mobile). Cart, wishlist,
        and AI recommendations stay in sync.
      </p>

      {ctx?.sync_message && (
        <div className="omni-status ok">{ctx.sync_message}</div>
      )}

      <div className="omni-stats">
        <div><span>{ctx?.cart_count ?? 0}</span> Cart</div>
        <div><span>{ctx?.wishlist_count ?? 0}</span> Wishlist</div>
        <div><span>{ctx?.viewed_count ?? 0}</span> Viewed</div>
      </div>

      {ctx?.channels_used && ctx.channels_used.length > 0 && (
        <div className="omni-active">
          <span className="omni-label">Active channels</span>
          {ctx.channels_used.map((ch) => (
            <span key={ch} className={`omni-pill ${ch === channel ? 'here' : ''}`}>
              {ch === 'oneshop' ? '🖥 OneShop' : '📱 OneApp'}
            </span>
          ))}
        </div>
      )}

      <div className="omni-session">
        <span className="omni-label">Session ID</span>
        <code>{ctx?.session_id?.slice(0, 8)}…{ctx?.session_id?.slice(-4)}</code>
      </div>

      <div className="omni-actions">
        <button type="button" className="omni-btn primary" onClick={openOther}>
          Open on {channel === 'oneshop' ? 'OneApp Mobile' : 'OneShop Web'}
        </button>
        <button
          type="button"
          className="omni-btn"
          onClick={() => copyLink(ctx?.continue_url_app || '', 'app')}
        >
          {copied === 'app' ? 'Copied!' : 'Copy mobile link'}
        </button>
        <button
          type="button"
          className="omni-btn"
          onClick={() => copyLink(ctx?.continue_url_web || '', 'web')}
        >
          {copied === 'web' ? 'Copied!' : 'Copy web link'}
        </button>
      </div>

      <div className="omni-link-customer">
        <span className="omni-label">Link customer (persistent identity)</span>
        <div className="omni-link-row">
          <input
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value)}
            placeholder="customer-id"
          />
          <button type="button" className="omni-btn" onClick={handleLink}>Link</button>
        </div>
        {ctx?.customer_id && (
          <p className="omni-linked">Linked as <strong>{ctx.customer_id}</strong></p>
        )}
      </div>
    </div>
  )
}
