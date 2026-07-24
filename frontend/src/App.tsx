import { useEffect, useState } from 'react'
import { getHealth, setChannel, type Channel } from './api'
import ChatPage from './pages/ChatPage'
import ShopPage from './pages/ShopPage'
import OmnichannelPanel from './components/OmnichannelPanel'
import './App.css'

type Tab = 'shop' | 'chat' | 'sync'

export default function App() {
  const [tab, setTab] = useState<Tab>('shop')
  const [llmMode, setLlmMode] = useState<string>('checking…')
  const [chatBootstrap, setChatBootstrap] = useState<string | null>(null)
  const [openCheckout, setOpenCheckout] = useState(false)
  const [shopRefreshKey, setShopRefreshKey] = useState(0)
  const channel: Channel = 'oneshop'

  useEffect(() => {
    setChannel('oneshop')
  }, [])

  useEffect(() => {
    getHealth()
      .then((h) => setLlmMode(h.llm_enabled ? 'AI powered' : 'Smart search'))
      .catch(() => setLlmMode('Offline'))
  }, [])

  const handleAskAssistant = (message: string) => {
    setChatBootstrap(message)
    setTab('chat')
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <span className="logo-icon">◆</span>
            <div>
              <h1>OneShop</h1>
              <span className="logo-sub">Omnichannel AI Engine</span>
            </div>
          </div>
          <nav className="nav-tabs">
            <button
              className={`nav-tab ${tab === 'shop' ? 'active' : ''}`}
              onClick={() => setTab('shop')}
            >
              Shop
            </button>
            <button
              className={`nav-tab ${tab === 'chat' ? 'active' : ''}`}
              onClick={() => setTab('chat')}
            >
              ShopAssist
            </button>
            <button
              className={`nav-tab ${tab === 'sync' ? 'active' : ''}`}
              onClick={() => setTab('sync')}
            >
              Sync
            </button>
          </nav>
        </div>
        <div className="header-right">
          <span className="mode-badge">{llmMode}</span>
          <span className="channel-badge">Web</span>
          <a href="/app" className="oneapp-link" target="_blank" rel="noreferrer">
            OneApp →
          </a>
        </div>
      </header>

      {tab === 'shop' ? (
        <ShopPage
          channel={channel}
          layout="desktop"
          onAskAssistant={handleAskAssistant}
          openCheckout={openCheckout}
          onCheckoutOpened={() => setOpenCheckout(false)}
          refreshKey={shopRefreshKey}
        />
      ) : tab === 'chat' ? (
        <ChatPage
          channel={channel}
          initialMessage={chatBootstrap}
          onConsumed={() => setChatBootstrap(null)}
          onCartUpdated={() => setShopRefreshKey((k) => k + 1)}
          onOpenCheckout={() => {
            setOpenCheckout(true)
            setShopRefreshKey((k) => k + 1)
            setTab('shop')
          }}
        />
      ) : (
        <div className="sync-page">
          <OmnichannelPanel channel={channel} />
        </div>
      )}
    </div>
  )
}
