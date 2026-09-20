import { useCallback, useEffect, useState } from 'react'
import { fetchSessions, type SessionSummary } from '../../../api'

/** The user's sessions, most recently active first. `refresh` re-fetches (e.g. after a reply). */
export function useSessions() {
  const [sessions, setSessions] = useState<SessionSummary[]>([])

  const refresh = useCallback(() => {
    fetchSessions()
      .then((res) => setSessions(res.sessions))
      .catch(() => {})
  }, [])

  useEffect(refresh, [refresh])

  return { sessions, refresh }
}
