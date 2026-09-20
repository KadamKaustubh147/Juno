import { useEffect, useState } from 'react'
import { fetchMe, type User } from '../../api'

/** The signed-in user's profile, or null until it loads (a 401 is handled by api.ts's handler). */
export function useMe() {
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    fetchMe()
      .then(setUser)
      .catch(() => {})
  }, [])

  return user
}
