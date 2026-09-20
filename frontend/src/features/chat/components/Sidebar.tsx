import type { SessionSummary, User } from '../../../api'
import { Button } from '../../../components/Button'
import { Logo } from '../../../components/Logo'

type Props = {
  /** null while the profile is still loading */
  user: User | null
  sessions: SessionSummary[]
  activeThread: string | null
  /** switching sessions is blocked while a reply is streaming */
  busy: boolean
  /** small screens: the sidebar is an off-canvas drawer */
  open: boolean
  onClose: () => void
  onNewSession: () => void
  onOpenSession: (sessionId: string) => void
  onLogout: () => void
}

export function Sidebar({
  user,
  sessions,
  activeThread,
  busy,
  open,
  onClose,
  onNewSession,
  onOpenSession,
  onLogout,
}: Props) {
  const name = user ? user.full_name || user.email.split('@')[0] : ''

  return (
    <>
      {open && <div onClick={onClose} className="fixed inset-0 z-10 bg-ink/30 md:hidden" aria-hidden />}
      <aside
        className={`fixed inset-y-0 left-0 z-20 flex w-64 shrink-0 flex-col gap-5 border-r border-line bg-cream p-5 transition-transform md:static md:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <Logo />
        <Button onClick={onNewSession} disabled={busy}>
          Start a session
        </Button>

        <div className="text-xs text-muted">Sessions</div>
        <ul className="-mt-2 flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto">
          {sessions.length === 0 && !activeThread && (
            <li className="px-3 text-xs text-muted">No sessions yet</li>
          )}
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                onClick={() => onOpenSession(s.id)}
                disabled={busy}
                className={`w-full rounded-lg px-3 py-2 text-left text-[13px] hover:bg-cream-dark ${
                  s.id === activeThread ? 'bg-cream-dark text-ink' : 'text-ink/70'
                }`}
              >
                <span className="block truncate">Session</span>
                <span className="block text-[11px] text-muted">
                  {new Date(s.last_at).toLocaleDateString()}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2.5 border-t border-line pt-4">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-sage-avatar text-sm text-sage uppercase">
            {name[0]}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold text-ink">{name}</div>
            <div className="truncate text-[11px] text-muted">{user?.email}</div>
          </div>
          <Button variant="ghost" size="sm" onClick={onLogout}>
            Log out
          </Button>
        </div>
      </aside>
    </>
  )
}
