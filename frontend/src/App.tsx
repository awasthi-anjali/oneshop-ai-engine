import { useEffect, useState } from 'react'
import { getHealth } from './api'
import ShopPage from './pages/ShopPage'
import './App.css'

export default function App() {
  const [llmMode, setLlmMode] = useState('Checking…')

  useEffect(() => {
    getHealth()
      .then((health) => setLlmMode(health.llm_enabled ? 'AI powered' : 'Smart fallback'))
      .catch(() => setLlmMode('Offline'))
  }, [])

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <div className="logo">
            <span className="logo-icon" aria-hidden="true">◆</span>
            <div>
              <h1>OneShop</h1>
              <span className="logo-sub">Omnichannel AI Engine</span>
            </div>
          </div>
        </div>
        <div className="header-right">
          <span className="mode-badge">{llmMode}</span>
          <span className="channel-badge">Web</span>
        </div>
      </header>
      <ShopPage />
    </div>
  )
}
