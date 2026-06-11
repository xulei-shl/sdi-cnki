import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import content from './content.md?raw'
import { ScrollArea } from '@/components/ui/scroll-area'
import { cn } from '@/lib/utils'

interface TocItem {
  id: string
  text: string
  level: number
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function extractHeadings(md: string): TocItem[] {
  const items: TocItem[] = []
  for (const line of md.split('\n')) {
    const m = line.match(/^(#{1,3})\s+(.+)/)
    if (m) {
      const level = m[1].length
      const text = m[2].replace(/[*_`]/g, '').trim()
      items.push({ id: slugify(text), text, level })
    }
  }
  return items
}

function Toc({ items, activeId }: { items: TocItem[]; activeId: string }) {
  return (
    <nav className="space-y-0.5">
      {items.map((item) => (
        <a
          key={item.id}
          href={`#${item.id}`}
          onClick={(e) => {
            e.preventDefault()
            document.getElementById(item.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
          }}
          className={cn(
            'block py-1 text-sm rounded transition-colors hover:text-foreground',
            item.level === 1 && 'pl-3 font-medium',
            item.level === 2 && 'pl-3',
            item.level === 3 && 'pl-6',
            activeId === item.id
              ? 'text-foreground font-medium border-l-2 border-foreground -ml-px'
              : 'text-muted-foreground border-l-2 border-transparent -ml-px',
          )}
        >
          {item.text}
        </a>
      ))}
    </nav>
  )
}

export default function UsageGuidePage() {
  const headings = useMemo(() => extractHeadings(content), [])
  const [activeId, setActiveId] = useState(headings[0]?.id ?? '')
  const contentRef = useRef<HTMLDivElement>(null)

  const handleScroll = useCallback(() => {
    if (!contentRef.current) return
    const container = contentRef.current
    let current = headings[0]?.id ?? ''
    for (const h of headings) {
      const el = document.getElementById(h.id)
      if (el) {
        const rect = el.getBoundingClientRect()
        const containerRect = container.getBoundingClientRect()
        if (rect.top - containerRect.top <= 80) {
          current = h.id
        }
      }
    }
    setActiveId(current)
  }, [headings])

  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    el.addEventListener('scroll', handleScroll, { passive: true })
    return () => el.removeEventListener('scroll', handleScroll)
  }, [handleScroll])

  return (
    <div className="h-full flex overflow-hidden">
      {/* Left: TOC sidebar */}
      <aside className="w-56 shrink-0 border-r bg-background hidden lg:block">
        <div className="px-4 py-4 border-b">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">目录</h3>
        </div>
        <ScrollArea className="h-[calc(100%-45px)]">
          <div className="px-3 py-3">
            <Toc items={headings} activeId={activeId} />
          </div>
        </ScrollArea>
      </aside>

      {/* Right: Content */}
      <div ref={contentRef} className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-8 py-8">
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children, ...props }) => {
                const text = String(children).replace(/[*_`]/g, '')
                return <h1 id={slugify(text)} className="text-2xl font-bold mt-8 mb-4 first:mt-0 scroll-mt-8" {...props}>{children}</h1>
              },
              h2: ({ children, ...props }) => {
                const text = String(children).replace(/[*_`]/g, '')
                return <h2 id={slugify(text)} className="text-xl font-semibold mt-8 mb-3 pb-2 border-b scroll-mt-8" {...props}>{children}</h2>
              },
              h3: ({ children, ...props }) => {
                const text = String(children).replace(/[*_`]/g, '')
                return <h3 id={slugify(text)} className="text-lg font-semibold mt-6 mb-2 scroll-mt-8" {...props}>{children}</h3>
              },
              table: ({ children, ...props }) => (
                <div className="overflow-x-auto my-4">
                  <table className="w-full text-sm border-collapse" {...props}>{children}</table>
                </div>
              ),
              thead: ({ children, ...props }) => <thead className="border-b bg-muted/50" {...props}>{children}</thead>,
              th: ({ children, ...props }) => <th className="px-3 py-2 text-left font-medium text-muted-foreground" {...props}>{children}</th>,
              td: ({ children, ...props }) => <td className="px-3 py-2 border-b" {...props}>{children}</td>,
              code: ({ children, className, ...props }) => {
                const isBlock = className?.includes('language-')
                if (isBlock) {
                  return <code className={cn('block bg-muted/50 rounded-md p-4 my-4 text-sm overflow-x-auto font-mono', className)} {...props}>{children}</code>
                }
                return <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono" {...props}>{children}</code>
              },
              pre: ({ children, ...props }) => <pre className="my-2" {...props}>{children}</pre>,
              ul: ({ children, ...props }) => <ul className="list-disc pl-6 my-3 space-y-1" {...props}>{children}</ul>,
              ol: ({ children, ...props }) => <ol className="list-decimal pl-6 my-3 space-y-1" {...props}>{children}</ol>,
              li: ({ children, ...props }) => <li className="text-sm leading-relaxed" {...props}>{children}</li>,
              p: ({ children, ...props }) => <p className="text-sm leading-relaxed my-3" {...props}>{children}</p>,
              blockquote: ({ children, ...props }) => (
                <blockquote className="border-l-4 border-primary/20 pl-4 my-4 text-muted-foreground italic" {...props}>{children}</blockquote>
              ),
              hr: () => <hr className="my-8 border-border" />,
              strong: ({ children, ...props }) => <strong className="font-semibold" {...props}>{children}</strong>,
            }}
          >
            {content}
          </Markdown>
        </div>
      </div>
    </div>
  )
}
