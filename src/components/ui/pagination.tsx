import { cn } from '@/lib/utils'

interface PaginationProps {
  current: number
  total: number
  pageSize: number
  onChange: (page: number) => void
}

function Pagination({ current, total, pageSize, onChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize)
  if (totalPages <= 1) return null

  const pages: (number | string)[] = []
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= current - 1 && i <= current + 1)) {
      pages.push(i)
    } else if (pages[pages.length - 1] !== '...') {
      pages.push('...')
    }
  }

  return (
    <div className="flex items-center justify-between px-2 py-4">
      <div className="text-sm text-muted-foreground">
        共 {total} 条
      </div>
      <div className="flex items-center gap-1">
        <button
          className={cn(
            'inline-flex items-center justify-center h-8 px-2 rounded text-sm whitespace-nowrap',
            current <= 1 ? 'text-muted-foreground cursor-not-allowed' : 'hover:bg-accent',
          )}
          disabled={current <= 1}
          onClick={() => onChange(current - 1)}
        >
          上一页
        </button>
        {pages.map((page, i) =>
          typeof page === 'number' ? (
            <button
              key={i}
              className={cn(
                'inline-flex items-center justify-center h-8 w-8 rounded text-sm',
                page === current ? 'bg-primary text-primary-foreground' : 'hover:bg-accent',
              )}
              onClick={() => onChange(page)}
            >
              {page}
            </button>
          ) : (
            <span key={i} className="px-1 text-muted-foreground">...</span>
          ),
        )}
        <button
          className={cn(
            'inline-flex items-center justify-center h-8 px-2 rounded text-sm whitespace-nowrap',
            current >= totalPages ? 'text-muted-foreground cursor-not-allowed' : 'hover:bg-accent',
          )}
          disabled={current >= totalPages}
          onClick={() => onChange(current + 1)}
        >
          下一页
        </button>
      </div>
    </div>
  )
}

export { Pagination }
