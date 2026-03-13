import DOMPurify from 'dompurify'
import { marked } from 'marked'

marked.setOptions({ breaks: true, gfm: true })

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

export function renderMarkdown(content: string): string {
  if (!content) return ''
  const raw = marked.parse(content, { async: false }) as string
  return DOMPurify.sanitize(raw)
}
