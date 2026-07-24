import { X } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Pagination } from '@/components/ui/pagination'
import { analysisTextColor, reviewTextColor, downloadTextColor, getAnalysisLabel, relevanceColor, DOWNLOAD_BADGE } from './constants'

interface ResultTableProps {
  results: any[]
  loading: boolean
  total: number
  page: number
  selectedIds: Set<number>
  downloadingIds: Set<number>
  onToggleSelect: (id: number) => void
  onToggleAll: () => void
  onClearSelection: () => void
  onViewDetail: (row: any) => void
  onSinglePass: (row: any) => void
  onSingleReject: (row: any) => void
  onSingleDownload: (row: any) => void
  onPageChange: (page: number) => void
}

export function ResultTable({
  results,
  loading,
  total,
  page,
  selectedIds,
  downloadingIds,
  onToggleSelect,
  onToggleAll,
  onClearSelection,
  onViewDetail,
  onSinglePass,
  onSingleReject,
  onSingleDownload,
  onPageChange,
}: ResultTableProps) {
  return (
    <div className="flex-1 overflow-auto px-8 py-6">
      {!loading && (
        <div className="pb-3 flex items-center gap-4">
          <span className="text-sm text-muted-foreground tabular-nums">
            {total > 0 ? (
              <>共 <span className="font-semibold text-foreground">{total}</span> 条结果</>
            ) : (
              '未找到匹配的结果'
            )}
          </span>
          {selectedIds.size > 0 && (
            <div className="flex items-center gap-1.5">
              <span className="text-sm font-medium text-primary">已选中 {selectedIds.size} 项</span>
              <button
                onClick={onClearSelection}
                className="p-1 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors text-muted-foreground"
                title="清空选择"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">
              <Checkbox
                checked={results.length > 0 && results.every(r => selectedIds.has(r.id))}
                ref={el => { if (el) el.indeterminate = results.some(r => selectedIds.has(r.id)) && !results.every(r => selectedIds.has(r.id)) }}
                onChange={onToggleAll}
              />
            </TableHead>
            <TableHead className="min-w-[350px] flex-1">题名</TableHead>
            <TableHead className="w-[180px]">期刊</TableHead>
            <TableHead className="w-[70px] text-center">出版年</TableHead>
            <TableHead className="w-[120px] text-center">相关性</TableHead>
            <TableHead className="w-[180px]">状态 <span className="text-xs font-normal text-muted-foreground">(分析/审核/下载)</span></TableHead>
            <TableHead className="w-[160px] text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center py-12">
                <div className="flex items-center justify-center gap-2 text-muted-foreground animate-pulse">
                  <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                  数据加载中...
                </div>
              </TableCell>
            </TableRow>
          ) : results.length === 0 ? (
            <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">暂无数据</TableCell></TableRow>
          ) : results.map((row) => {
            const score = row.llm_analysis?.parsed_result?.relevance_score ?? null
            return (
              <TableRow key={row.id} className="cursor-pointer" onClick={() => onViewDetail(row)}>
                <TableCell onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                  <Checkbox checked={selectedIds.has(row.id)} onChange={() => onToggleSelect(row.id)} />
                </TableCell>
                <TableCell>
                  <div className="truncate max-w-none" title={row.title}>
                    {row.title}
                    {row.is_duplicate && <Badge variant="warning" className="ml-1 text-xs">重复</Badge>}
                  </div>
                </TableCell>
                <TableCell className="truncate max-w-[180px]">{row.source_journal || '-'}</TableCell>
                <TableCell className="text-center">{row.publish_year ?? '-'}</TableCell>
                <TableCell className="text-center">
                  <span className={`text-xs ${relevanceColor(score)}`}>{score ?? '-'}</span>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1 text-xs">
                    <span className={analysisTextColor(row.llm_analysis?.status, row.llm_analysis?.parsed_result?.is_target_topic)}>
                      {getAnalysisLabel(row.llm_analysis?.status, row.llm_analysis?.parsed_result)}
                    </span>
                    <span className="text-muted-foreground">/</span>
                    <span className={reviewTextColor(row.is_passed)}>
                      {row.is_passed === true ? '通过' : row.is_passed === false ? '拒绝' : '未审'}
                    </span>
                    <span className="text-muted-foreground">/</span>
                    <span className={downloadTextColor(row.download?.download_status)}>
                      {DOWNLOAD_BADGE[row.download?.download_status || 'pending'].label}
                    </span>
                  </div>
                </TableCell>
                <TableCell onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                  <div className="flex justify-end gap-3">
                    {row.is_passed === true && row.download?.download_status !== 'completed' && row.download?.download_status !== 'downloading' && (
                      <Button variant="link" className="h-auto p-0 font-normal text-amber-600 hover:text-amber-700" disabled={downloadingIds.has(row.id)} onClick={() => onSingleDownload(row)}>
                        {downloadingIds.has(row.id) ? '下载中...' : '下载'}
                      </Button>
                    )}
                    <Button variant="link" className="h-auto p-0 font-normal" onClick={() => onSinglePass(row)}>通过</Button>
                    <Button variant="link" className="h-auto p-0 font-normal text-destructive hover:text-destructive/80" onClick={() => onSingleReject(row)}>拒绝</Button>
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      <Pagination current={page} total={total} pageSize={20} onChange={onPageChange} />
    </div>
  )
}
