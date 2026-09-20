import { useState, type FormEvent } from 'react'

type Props = {
  /** a reply is streaming: typing is fine, sending waits */
  disabled: boolean
  /** the script has finished: nothing more can be sent in this session */
  ended: boolean
  onSend: (text: string) => void
}

export function Composer({ disabled, ended, onSend }: Props) {
  const [draft, setDraft] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text || disabled) return
    onSend(text)
    setDraft('')
  }

  if (ended) {
    return (
      <footer className="border-t border-line px-4 pt-4 pb-5 text-center text-sm text-muted md:px-6">
        This session has ended. Start a new session to keep talking.
      </footer>
    )
  }

  return (
    <form onSubmit={submit} className="flex gap-2.5 border-t border-line px-4 pt-4 pb-5 md:px-6">
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Type a message"
        aria-label="Message"
        className="flex-1 rounded-full bg-cream px-5 py-3.5 text-sm text-ink placeholder:text-muted"
      />
      <button
        type="submit"
        disabled={disabled}
        aria-label="Send"
        className="size-[46px] shrink-0 rounded-full bg-sage text-lg text-cream hover:bg-sage-dark disabled:opacity-50"
      >
        ↑
      </button>
    </form>
  )
}
