export function Logo() {
  return (
    <div className="flex items-center gap-2.5 text-ink">
      {/* the wordmark next to it already says "Juno", so the mark is decorative */}
      <img src="/juno-logo.svg" alt="" className="size-9 shrink-0" />
      <span className="font-serif text-xl font-medium">Juno</span>
    </div>
  )
}
