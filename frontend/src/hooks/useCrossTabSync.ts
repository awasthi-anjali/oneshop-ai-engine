import { useEffect } from 'react'
import { onSessionSync } from '../api'

/** Refresh when another tab (OneShop / OneApp) updates the shared session. */
export function useCrossTabSync(onSync: () => void) {
  useEffect(() => {
    return onSessionSync(onSync)
  }, [onSync])
}
