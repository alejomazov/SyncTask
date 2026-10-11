import type { ComponentProps } from 'react'
import Markdown, { type ExtraProps } from 'react-markdown'
import remarkGfm from 'remark-gfm'

// `node` is react-markdown's syntax tree entry; it must not reach the DOM element.
function ExternalLink({ node, ...props }: ComponentProps<'a'> & ExtraProps) {
  void node
  return <a {...props} target="_blank" rel="noreferrer" />
}

function ScrollableTable({ node, ...props }: ComponentProps<'table'> & ExtraProps) {
  void node
  return (
    <div className="markdown-table">
      <table {...props} />
    </div>
  )
}

/** A reply of the assistant, with its Markdown shown as tables, lists, bold text and so on. */
export default function AssistantMessage({ text }: { text: string }) {
  return (
    <div className="chat-bubble chat-assistant markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        // Replies may quote text from emails: remote images could leak data when loaded.
        disallowedElements={['img']}
        components={{ a: ExternalLink, table: ScrollableTable }}
      >
        {text}
      </Markdown>
    </div>
  )
}
