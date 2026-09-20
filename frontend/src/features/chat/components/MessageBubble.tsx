import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatMsg } from '../../../api'

// Tight variants of the default markdown elements -- the browser/prose defaults add
// margins sized for full documents, which looks wrong inside a compact chat bubble.
const markdownComponents = {
  p: ({ ...props }) => <p className="[&:not(:last-child)]:mb-2" {...props} />,
  ul: ({ ...props }) => <ul className="mb-2 list-disc pl-5 last:mb-0" {...props} />,
  ol: ({ ...props }) => <ol className="mb-2 list-decimal pl-5 last:mb-0" {...props} />,
  li: ({ ...props }) => <li className="mb-0.5" {...props} />,
  a: ({ ...props }) => <a className="underline" target="_blank" rel="noreferrer" {...props} />,
  code: ({ ...props }) => <code className="rounded bg-black/10 px-1 py-0.5 text-[0.9em]" {...props} />,
  pre: ({ ...props }) => (
    <pre className="mb-2 overflow-x-auto rounded-lg bg-black/10 p-2 text-[0.9em] last:mb-0" {...props} />
  ),
}

type Props = {
  role: ChatMsg['role']
  content: string
  /** an empty assistant bubble shows an ellipsis while a reply is still on its way */
  pending?: boolean
}

export function MessageBubble({ role, content, pending }: Props) {
  const isAssistant = role === 'assistant'
  return (
    <div className={`flex ${isAssistant ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed md:max-w-[62%] ${
          isAssistant
            ? 'rounded-tl-md bg-sage-light font-serif text-sage-dark'
            : 'rounded-tr-md bg-white text-ink shadow-sm'
        }`}
      >
        {isAssistant ? (
          content ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {content}
            </ReactMarkdown>
          ) : (
            pending && '…'
          )
        ) : (
          content
        )}
      </div>
    </div>
  )
}
