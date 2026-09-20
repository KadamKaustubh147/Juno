type Props = {
  onMenu: () => void
}

export function ChatHeader({ onMenu }: Props) {
  return (
    <header className="flex items-center justify-between border-b border-line px-4 py-3.5 md:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenu}
          aria-label="Open sessions"
          className="rounded-lg px-2 py-1 text-lg text-ink/70 hover:bg-cream-dark md:hidden"
        >
          ☰
        </button>
        <div className="flex items-baseline gap-2">
          <strong className="text-sm text-ink">Session</strong>
          <span className="text-[13px] text-muted">text</span>
        </div>
      </div>
      <button className="rounded-full border border-line bg-cream px-3.5 py-1.5 text-[13px] text-ink/70">
        English <span className="text-[10px] text-muted">▾</span>
      </button>
    </header>
  )
}
