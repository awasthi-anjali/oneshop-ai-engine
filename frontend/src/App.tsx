import { useEffect, useState } from 'react'
import { getHealth } from './api'
import ChatPage from './pages/ChatPage'
import ShopPage from './pages/ShopPage'
import './App.css'

type Tab = 'shop' | 'chat'

export default function App() {
  const [tab, setTab] = useState<Tab>('shop')
  const [llmMode, setLlmMode] = useState<string>('checking…')
  const [chatBootstrap, setChatBootstrap] = useState<string | null>(null)
  const [openCheckout, setOpenCheckout] = useState(false)

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
          </nav>
        </div>
        <div className="header-right">
          <span className="mode-badge">{llmMode}</span>
          <span className="channel-badge">Web</span>
        </div>
      </header>

      {tab === 'shop' ? (
        <ShopPage
          onAskAssistant={handleAskAssistant}
          openCheckout={openCheckout}
          onCheckoutOpened={() => setOpenCheckout(false)}
        />
      ) : (
        <ChatPage
          initialMessage={chatBootstrap}
          onConsumed={() => setChatBootstrap(null)}
          onOpenCheckout={() => {
            setOpenCheckout(true)
            setTab('shop')
          }}
        />
      )}
    </div>
  )
}
