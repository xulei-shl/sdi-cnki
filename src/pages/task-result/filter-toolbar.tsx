import { ChevronDown } from 'lucide-react'
import { Select } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { ANALYSIS_FILTER_OPTIONS, ANALYSIS_RESULT_OPTIONS, REVIEW_OPTIONS, DOWNLOAD_STATUS_OPTIONS, SCORE_OPTIONS } from './constants'

interface FilterToolbarProps {
  analysisStatus: string
  analysisResult: string
  minScore: string
  reviewStatus: string
  downloadStatus: string
  keyword: string
  publishYear: string
  includeDuplicate: boolean
  selectedCount: number
  moreOpen: boolean
  exporting: boolean
  retrying: boolean
  canDownload: boolean
  canShowMore: boolean
  canRetryAnalysis: boolean
  onAnalysisStatusChange: (v: string) => void
  onAnalysisResultChange: (v: string) => void
  onMinScoreChange: (v: string) => void
  onReviewStatusChange: (v: string) => void
  onDownloadStatusChange: (v: string) => void
  onKeywordChange: (v: string) => void
  onPublishYearChange: (v: string) => void
  onIncludeDuplicateChange: (v: boolean) => void
  onBatchPass: () => void
  onBatchReject: () => void
  onDownload: () => void
  onExport: () => void
  onRetryAnalysis: () => void
  onMoreToggle: () => void
  onMoreClose: () => void
}

export function FilterToolbar({
  analysisStatus,
  analysisResult,
  minScore,
  reviewStatus,
  downloadStatus,
  keyword,
  publishYear,
  includeDuplicate,
  selectedCount,
  moreOpen,
  exporting,
  retrying,
  canDownload,
  canShowMore,
  canRetryAnalysis,
  onAnalysisStatusChange,
  onAnalysisResultChange,
  onMinScoreChange,
  onReviewStatusChange,
  onDownloadStatusChange,
  onKeywordChange,
  onPublishYearChange,
  onIncludeDuplicateChange,
  onBatchPass,
  onBatchReject,
  onDownload,
  onExport,
  onRetryAnalysis,
  onMoreToggle,
  onMoreClose,
}: FilterToolbarProps) {
  return (
    <div className="px-8 py-5 border-b flex items-center justify-between flex-wrap gap-6 shrink-0">
      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <Select value={analysisStatus} onChange={(e) => { onAnalysisStatusChange(e.target.value) }} className="w-[120px]">
          {ANALYSIS_FILTER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <Select value={analysisResult} onChange={(e) => { onAnalysisResultChange(e.target.value) }} className="w-[120px]">
          {ANALYSIS_RESULT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <Select value={minScore} onChange={(e) => { onMinScoreChange(e.target.value) }} className="w-[100px]">
          {SCORE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <div className="w-px h-5 bg-border mx-1" />
        <Select value={reviewStatus} onChange={(e) => { onReviewStatusChange(e.target.value) }} className="w-[120px]">
          {REVIEW_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <Select value={downloadStatus} onChange={(e) => { onDownloadStatusChange(e.target.value) }} className="w-[120px]">
          {DOWNLOAD_STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </Select>
        <div className="w-px h-5 bg-border mx-1" />
        <Input placeholder="题名关键词" value={keyword} onChange={(e) => { onKeywordChange(e.target.value) }} className="w-[150px]" />
        <Input placeholder="年份" value={publishYear} onChange={(e) => { onPublishYearChange(e.target.value) }} className="w-[80px]" />
        <label className="flex items-center gap-1 text-sm bg-accent/50 px-2 py-1.5 rounded-md cursor-pointer hover:bg-accent/80 transition-colors">
          <Checkbox checked={includeDuplicate} onChange={(e) => { onIncludeDuplicateChange(e.target.checked) }} />
          <span className="ml-1">含重复</span>
        </label>
      </div>

      {/* Batch Actions */}
      <div className="flex items-center gap-3">
        <Button size="sm" variant="outline" disabled={selectedCount === 0} onClick={onBatchPass}>批量通过</Button>
        <Button size="sm" variant="outline" disabled={selectedCount === 0} onClick={onBatchReject}>批量拒绝</Button>
        {canDownload && (
          <Button size="sm" variant="outline" onClick={onDownload}>PDF 下载</Button>
        )}
        {canShowMore && (
          <div className="relative">
            <Button size="sm" variant="outline" onClick={onMoreToggle}>
              更多 <ChevronDown className="h-3 w-3" />
            </Button>
            {moreOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={onMoreClose} />
                <div className="absolute right-0 top-full mt-1 z-50 min-w-[130px] rounded-md border bg-popover p-1 shadow-md">
                  <button
                    className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground disabled:opacity-50 disabled:pointer-events-none"
                    onClick={onExport}
                    disabled={exporting}
                  >
                    {exporting ? '导出中...' : '结果导出'}
                  </button>
                  {canRetryAnalysis && (
                    <button
                      className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground disabled:opacity-50 disabled:pointer-events-none"
                      onClick={onRetryAnalysis}
                      disabled={retrying}
                    >
                      {retrying ? '分析中...' : 'LLM 分析'}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
