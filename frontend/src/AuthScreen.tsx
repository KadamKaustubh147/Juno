import { useState, type FormEvent } from 'react'
import { login, register, type User } from './api'
import { Logo } from './components/Logo'

type Mode = 'login' | 'register'

type Props = {
  initialMode?: Mode
  onAuthenticated: (user: User) => void
  onBack: () => void
}

export default function AuthScreen({ initialMode = 'login', onAuthenticated, onBack }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const user =
        mode === 'login'
          ? await login(email, password)
          : await register(email, password, fullName.trim())
      onAuthenticated(user)
    } catch (err) {
      setError(
        err instanceof Error && 'status' in err
          ? err.message
          : "Can't reach the server. Check your connection and try again.",
      )
      setBusy(false)
    }
  }

  const input =
    'w-full rounded-[10px] bg-cream px-4 py-3 text-sm text-ink placeholder:text-muted'

  return (
    <div className="grid min-h-svh place-items-center bg-cream-dark p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <Logo />
        <form
          onSubmit={submit}
          className="flex flex-col gap-3.5 rounded-2xl border border-line bg-white p-7 shadow-sm"
        >
          <h1 className="font-serif text-2xl text-sage-dark">
            {mode === 'login' ? 'Welcome back' : 'Create an account'}
          </h1>

          {mode === 'register' && (
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Name (optional)"
              aria-label="Name"
              autoComplete="name"
              className={input}
            />
          )}
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            aria-label="Email"
            autoComplete="email"
            className={input}
          />
          <input
            type="password"
            required
            minLength={mode === 'register' ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === 'register' ? 'Password (8+ characters)' : 'Password'}
            aria-label="Password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            className={input}
          />

          {error && (
            <p role="alert" className="border-l-2 border-ink pl-3 text-[13px] font-medium text-ink">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={busy}
            className="rounded-[10px] bg-sage py-3 text-sm font-semibold text-cream hover:bg-sage-dark disabled:opacity-60"
          >
            {mode === 'login' ? 'Log in' : 'Sign up'}
          </button>
          <button
            type="button"
            onClick={() => {
              setMode(mode === 'login' ? 'register' : 'login')
              setError('')
            }}
            className="text-[13px] text-muted hover:text-ink"
          >
            {mode === 'login' ? 'New here? Create an account' : 'Have an account? Log in'}
          </button>
        </form>
        <button type="button" onClick={onBack} className="self-start text-[13px] text-muted hover:text-ink">
          Back to home
        </button>
      </div>
    </div>
  )
}
