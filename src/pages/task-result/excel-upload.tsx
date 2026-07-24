import { Button } from '@/components/ui/button'

interface ExcelUploadProps {
  uploadFile: File | null
  importing: boolean
  importError: string | null
  onFileChange: (file: File | null) => void
  onImport: () => void
}

export function ExcelUpload({ uploadFile, importing, importError, onFileChange, onImport }: ExcelUploadProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-12">
      <div className="max-w-md w-full space-y-6">
        <div className="text-center">
          <h3 className="text-lg font-medium">Excel 数据导入</h3>
          <p className="text-sm text-muted-foreground mt-1">
            上传 CNKI 导出的 .xlsx 文件，导入后自动执行查重和 LLM 分析
          </p>
        </div>

        <div className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary/50 transition-colors">
          <input
            type="file"
            accept=".xlsx,.xls,.csv"
            onChange={(e) => {
              onFileChange(e.target.files?.[0] || null)
            }}
            className="hidden"
            id="excel-upload"
          />
          <label htmlFor="excel-upload" className="cursor-pointer block">
            {uploadFile ? (
              <div>
                <p className="font-medium">{uploadFile.name}</p>
                <p className="text-sm text-muted-foreground mt-1">点击重新选择</p>
              </div>
            ) : (
              <div>
                <p className="font-medium">点击选择文件</p>
                <p className="text-sm text-muted-foreground mt-1">支持 .xlsx、.xls、.csv 格式，最多 500 条数据</p>
              </div>
            )}
          </label>
        </div>

        <Button className="w-full" onClick={onImport} disabled={!uploadFile || importing}>
          {importing ? '导入中...' : '开始导入'}
        </Button>

        {importError && (
          <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-3 text-sm text-destructive">
            {importError}
          </div>
        )}

        <div className="bg-muted/30 rounded-lg p-4 text-sm text-muted-foreground space-y-1">
          <p>提示：</p>
          <ul className="list-disc list-inside space-y-0.5">
            <li>仅支持「确认后运行」创建的未执行任务实例</li>
            <li>请上传 CNKI 检索结果导出的 .xlsx、.xls 或 .csv 文件</li>
            <li>导入后将自动执行数据查重和 LLM 智能分析</li>
            <li>后续流程：审核 → PDF 下载 → 导出</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
