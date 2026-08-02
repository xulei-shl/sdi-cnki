import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { DOWNLOAD_BADGE } from './constants'

const LLM_LABEL_MAP: Record<string, string> = {
  is_target_topic: '是否相关',
  relevance_score: '相关性评分',
  relevance_level: '相关性等级',
  reasoning: '分析理由',
  domain_keywords: '领域关键词',
}

interface ResultDetailPanelProps {
  showDetail: boolean
  activeResult: any
  activeIndex: number
  totalResults: number
  onClose: () => void
  onPass: () => void
  onReject: () => void
  onPrev: () => void
  onNext: () => void
}

export function ResultDetailPanel({
  showDetail,
  activeResult,
  activeIndex,
  totalResults,
  onClose,
  onPass,
  onReject,
  onPrev,
  onNext,
}: ResultDetailPanelProps) {
  return (
    <DetailPanel
      open={showDetail}
      title={activeResult?.title || ''}
      onClose={onClose}
      width={640}
      headerActions={
        <div className="flex items-center gap-1.5">
          <button
            onClick={onPass}
            disabled={!activeResult || activeResult.is_passed === true}
            className="text-xs font-medium text-green-600 hover:text-green-700 transition-colors px-2 py-1 rounded-md hover:bg-green-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            通过
          </button>
          <button
            onClick={onReject}
            disabled={!activeResult || activeResult.is_passed === false}
            className="text-xs font-medium text-destructive hover:text-destructive/80 transition-colors px-2 py-1 rounded-md hover:bg-destructive/5 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            拒绝
          </button>
          <div className="w-px h-4 bg-border mx-0.5" />
          <button
            onClick={onPrev}
            disabled={activeIndex <= 0}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="上一条"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={onNext}
            disabled={activeIndex >= totalResults - 1}
            className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="下一条"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          {totalResults > 0 && (
            <span className="text-xs text-muted-foreground tabular-nums whitespace-nowrap min-w-[3.5rem] text-center">
              {activeIndex + 1}/{totalResults}
            </span>
          )}
        </div>
      }
    >
      {activeResult && (
        <>
          <DetailSection label="文献信息">
            <DetailRow label="题名" layout="vertical">{activeResult.title}</DetailRow>
            <DetailRow label="摘要" layout="vertical">
              {activeResult.abstract || '-'}
            </DetailRow>
            <DetailRow label="关键词" layout="vertical">{activeResult.keywords || '-'}</DetailRow>
            <DetailRow label="作者" valueAlign="left">{activeResult.authors || '-'}</DetailRow>
            <DetailRow label="期刊" valueAlign="left">{activeResult.source_journal || '-'}</DetailRow>
            <DetailRow label="出版年" valueAlign="left">{activeResult.publish_year ?? '-'}</DetailRow>
            <DetailRow label="作者单位" layout="vertical">{activeResult.organ || '-'}</DetailRow>
            <DetailRow label="基金" layout="vertical">{activeResult.fund || '-'}</DetailRow>
            <DetailRow label="原文链接" valueAlign="left">
              {activeResult.original_url ? (
                <a href={activeResult.original_url} target="_blank" rel="noopener noreferrer" className="text-primary underline hover:text-primary/80 transition-colors truncate block max-w-[420px]" title={activeResult.original_url}>
                  {activeResult.original_url}
                </a>
              ) : '-'}
            </DetailRow>
          </DetailSection>

          <Separator />

          <DetailSection label="LLM 分析结果">
            {activeResult.llm_analysis?.parsed_result ? (
              <div className="space-y-0.5">
                {Object.entries(activeResult.llm_analysis.parsed_result).map(([key, val]) => {
                  const isLongText = typeof val === 'string' && val.length > 30
                  return (
                    <DetailRow key={key} label={LLM_LABEL_MAP[key] ?? key} layout={isLongText ? 'vertical' : 'horizontal'} valueAlign="left">
                      {['High', 'Medium', 'Low', 'Irrelevant'].includes(String(val)) ? (
                        <Badge variant={val === 'High' ? 'success' : val === 'Medium' ? 'info' : val === 'Low' ? 'secondary' : 'destructive'} className="text-xs">
                          {String(val)}
                        </Badge>
                      ) : (
                        String(val)
                      )}
                    </DetailRow>
                  )
                })}
              </div>
            ) : activeResult.llm_analysis?.status === 'failed' ? (
              <p className="text-sm text-destructive px-3 py-2">分析失败: {activeResult.llm_analysis.error_message || '未知错误'}</p>
            ) : (
              <p className="text-sm text-muted-foreground px-3 py-2">暂无分析结果</p>
            )}
          </DetailSection>

          <Separator />

          <DetailSection label="下载信息">
            <DetailRow label="下载状态" valueAlign="left">
              <Badge variant={DOWNLOAD_BADGE[activeResult.download?.download_status || 'pending'].variant} className="text-xs">
                {DOWNLOAD_BADGE[activeResult.download?.download_status || 'pending'].label}
              </Badge>
            </DetailRow>
            <DetailRow label="文件路径" layout="vertical">{activeResult.download?.pdf_path || '-'}</DetailRow>
            <DetailRow label="文件大小" valueAlign="left">
              {activeResult.download?.file_size ? `${activeResult.download.file_size} KB` : '-'}
            </DetailRow>
            {activeResult.download?.download_status === 'failed' && activeResult.download?.error_message && (
              <DetailRow label="失败原因" layout="vertical">
                <span className="text-destructive text-sm">{activeResult.download.error_message}</span>
              </DetailRow>
            )}
          </DetailSection>
        </>
      )}
    </DetailPanel>
  )
}
