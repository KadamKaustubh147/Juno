import { Button } from '../components/Button'
import { Logo } from '../components/Logo'
import { MessageBubble } from '../features/chat/components/MessageBubble'

const points = [
  {
    title: 'Guided, not open-ended',
    body: 'Sessions follow a structured script drawn from cognitive behavioural therapy, and move on only when a step is done.',
  },
  {
    title: 'Remembers what you share',
    body: 'Juno keeps the details that matter, so you don’t have to start over each time you come back.',
  },
  {
    title: 'Pick up where you left off',
    body: 'Every session is saved. Close the tab and return to the same conversation later.',
  },
]

type Props = {
  onLogin: () => void
  onSignup: () => void
}

export function LandingPage({ onLogin, onSignup }: Props) {
  return (
    <div className="min-h-svh bg-cream text-ink">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <Logo />
        <nav className="flex items-center gap-2">
          <Button variant="ghost" onClick={onLogin}>
            Log in
          </Button>
          <Button onClick={onSignup}>Sign up</Button>
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6">
        <section className="grid items-center gap-12 py-14 md:py-24 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
          <div>
            <h1 className="font-serif text-5xl leading-[1.05] tracking-tight text-sage-dark sm:text-6xl">
              A quiet place to talk things through.
            </h1>
            <p className="mt-6 max-w-[46ch] text-lg leading-relaxed text-ink/70">
              Juno is an AI companion that guides you through structured, CBT-style conversations at
              your own pace, whenever you need them.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button size="lg" onClick={onSignup}>
                Start a session
              </Button>
              <Button variant="secondary" size="lg" onClick={onLogin}>
                Log in
              </Button>
            </div>
          </div>

          <figure className="rounded-3xl bg-cream-dark p-5 md:p-8">
            <div className="flex flex-col gap-2.5">
              <MessageBubble role="user" content="I keep replaying the meeting from this morning." />
              <MessageBubble
                role="assistant"
                content="That sounds like it’s staying with you. What part keeps coming back?"
              />
              <MessageBubble role="user" content="Mostly what I said in the first five minutes." />
            </div>
            <figcaption className="mt-5 text-xs text-muted">An example conversation</figcaption>
          </figure>
        </section>

        <section className="grid gap-8 border-t border-line py-12 md:grid-cols-3 md:gap-10">
          {points.map((p) => (
            <div key={p.title}>
              <h2 className="font-serif text-lg text-sage-dark">{p.title}</h2>
              <p className="mt-2 max-w-[38ch] text-sm leading-relaxed text-ink/70">{p.body}</p>
            </div>
          ))}
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-6 pt-4 pb-10">
        <p className="max-w-[64ch] text-xs leading-relaxed text-muted">
          Juno is an AI companion, not a licensed therapist or a crisis service. If you are in
          immediate danger, contact your local emergency number.
        </p>
      </footer>
    </div>
  )
}
