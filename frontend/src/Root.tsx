import { useEffect, useState } from 'react'
import AuthScreen from './AuthScreen'
import { getToken, logout, setUnauthorizedHandler } from './api'
import { ChatPage } from './pages/ChatPage'
import { LandingPage } from './pages/LandingPage'

/**
 * Signed in: the chat. Signed out: the landing page, or the login / sign-up screen once the
 * visitor picks one. There's no router -- three screens and one flag don't need one.
 */
export default function Root() {
  const [signedIn, setSignedIn] = useState(() => getToken() !== null)
  // which auth screen is open; null shows the landing page
  const [authMode, setAuthMode] = useState<'login' | 'register' | null>(null)

  useEffect(() => {
    // the server stopped accepting our token: back to the login screen
    setUnauthorizedHandler(() => {
      setSignedIn(false)
      setAuthMode('login')
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  if (signedIn) {
    return (
      <ChatPage
        onLogout={() => {
          logout()
          setSignedIn(false)
        }}
      />
    )
  }

  if (authMode) {
    return (
      <AuthScreen
        initialMode={authMode}
        onBack={() => setAuthMode(null)}
        onAuthenticated={() => {
          setSignedIn(true)
          setAuthMode(null)
        }}
      />
    )
  }

  return <LandingPage onLogin={() => setAuthMode('login')} onSignup={() => setAuthMode('register')} />
}
