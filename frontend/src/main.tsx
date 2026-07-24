import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import OneApp from './OneApp'
import './OneApp.css'
import { initSessionFromUrl, setChannel, ensureSessionId } from './api'
import './index.css'

ensureSessionId()
initSessionFromUrl()

const isOneApp = window.location.pathname.startsWith('/app')
if (isOneApp) {
  setChannel('oneapp')
} else {
  setChannel('oneshop')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isOneApp ? <OneApp /> : <App />}
  </StrictMode>,
)
