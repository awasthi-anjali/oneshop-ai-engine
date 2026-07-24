import { useEffect, useState } from 'react'
import { getHealth, setChannel, type Channel } from './api'
import ChatPage from './pages/ChatPage'
import ShopPage from './pages/ShopPage'
import OmnichannelPanel from './components/OmnichannelPanel'
import './OneApp.css'

type Tab = 'shop' | 'assist' | 'sync'

export default function OneApp() {
  const [tab, setTab] = useState<Tab>('shop')
  const [llmMode, setLlmMode] = useState('checking…')
  const [openCheckout, setOpenCheckout] = useState(false)
  const [shopRefreshKey, setShopRefreshKey] = useState(0)
  const channel: Channel = 'oneapp'

  useEffect(() => {
    setChannel('oneapp')
  }, [])

  useEffect(() => {
    getHealth()
      .then((h) => setLlmMode(h.llm_enabled ? 'AI powered' : 'Smart search'))
      .catch(() => setLlmMode('Offline'))
  }, [])

  return (
    <div className="oneapp">
      <header className="oneapp-header">
        <div>
          <h1>OneApp</h1>
          <span className="oneapp-sub">Mobile · Omnichannel</span>
        </div>
        <div className="oneapp-badges">
          <span className="mode-badge">{llmMode}</span>
          <span className="channel-badge mobile">Mobile</span>
        </div>
      </header>

      <main className="oneapp-main">
        {tab === 'shop' && (
          <ShopPage
            channel={channel}
            layout="mobile"
            openCheckout={openCheckout}
            onCheckoutOpened={() => setOpenCheckout(false)}
            refreshKey={shopRefreshKey}
          />
        )}
        {tab === 'assist' && (
          <ChatPage
            channel={channel}
            onCartUpdated={() => setShopRefreshKey((k) => k + 1)}
            onOpenCheckout={() => {
              setOpenCheckout(true)
              setShopRefreshKey((k) => k + 1)
              setTab('shop')
            }}
          />
        )}
        {tab === 'sync' && <OmnichannelPanel channel={channel} />}
      </main>

      <nav className="oneapp-nav">
        <button
          type="button"
          className={tab === 'shop' ? 'active' : ''}
          onClick={() => setTab('shop')}
        >
          <span>🛍</span> Shop
        </button>
        <button
          type="button"
          className={tab === 'assist' ? 'active' : ''}
          onClick={() => setTab('assist')}
        >
          <span>💬</span> Assist
        </button>
        <button
          type="button"
          className={tab === 'sync' ? 'active' : ''}
          onClick={() => setTab('sync')}
        >
          <span>⟳</span> Sync
        </button>
      </nav>

      <a className="oneapp-web-link" href="/">
        Open OneShop Web →
      </a>
    </div>
  )
}
