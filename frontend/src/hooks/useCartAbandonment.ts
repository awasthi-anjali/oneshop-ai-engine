import { useEffect } from 'react'
import { getStoredSessionId, markCartAbandoned } from '../api'

export function useCartAbandonmentTracking(cartCount: number, sessionId: string | null) {
  useEffect(() => {
    if (cartCount === 0) return

    const sid = sessionId || getStoredSessionId()

    const handleLeave = () => {
      const params = sid ? `?session_id=${sid}` : ''
      navigator.sendBeacon(`${window.location.origin}/api/checkout/abandon${params}`, '')
    }

    const handleVisibility = () => {
      if (document.visibilityState === 'hidden' && cartCount > 0) {
        markCartAbandoned(sid).catch(() => {})
      }
    }

    window.addEventListener('beforeunload', handleLeave)
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      window.removeEventListener('beforeunload', handleLeave)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [cartCount, sessionId])
}
