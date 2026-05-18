export type UserRole = 'admin' | 'user'

export interface User {
  id: number
  username: string
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user: User
}

export interface MetaTask {
  id: number
  name: string
  description: string | null
  creator_id: number
  creator_name: string
  prompt_template_id: number | null
  prompt_template_name: string | null
  search_params: SearchParams
  schedule_cron: string | null
  is_periodic: boolean
  is_active: boolean
  last_executed_at: string | null
  execution_count: number
  llm_configs: LlmConfigItem[]
  created_at: string
  updated_at: string
}

export interface SearchParams {
  query: string
  year_from?: number | null
  year_to?: number | null
  date_range?: string | null
  core_only?: boolean
  core_sources?: string[]
  synonym_extend?: boolean
  include_no_fulltext?: boolean
  max_export: number
}

export interface LlmConfigItem {
  id: number
  priority: number
  name: string
}

export interface TaskInstance {
  id: number
  meta_task_id: number
  meta_task_name: string
  creator_id: number
  creator_name: string
  instance_no: string
  status: TaskStatus
  auto_run: boolean
  execution_params: any
  search_result_file_path: string | null
  search_result_count: number
  valid_data_count: number
  duplicate_count: number
  llm_analysis_completed_count?: number
  llm_analysis_passed_count?: number
  llm_analysis_rejected_count?: number
  llm_analysis_failed_count?: number
  manual_review_passed_count?: number
  manual_review_rejected_count?: number
  download_success_count?: number
  download_failed_count?: number
  download_skipped_count?: number
  download_pending_count?: number
  error_message: string | null
  started_at: string | null
  search_completed_at: string | null
  analysis_completed_at: string | null
  download_started_at: string | null
  completed_at: string | null
  created_at: string
}

export type TaskStatus =
  | 'pending'
  | 'search_queued'
  | 'running'
  | 'search_completed'
  | 'analyzing'
  | 'analyzing_completed'
  | 'download_queued'
  | 'downloading'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface TaskResult {
  id: number
  task_instance_id: number
  title: string
  authors: string
  organ: string | null
  source_journal: string
  publish_year: number
  keywords: string | null
  abstract: string | null
  doi: string | null
  original_url: string | null
  is_duplicate: boolean
  duplicate_of_id: number | null
  reference_format: string | null
  analysis_status: AnalysisStatus
  is_passed: boolean | null
  download_status: DownloadStatus
  relevance_score: number | null
  relevance_level: string | null
}

export type AnalysisStatus = 'pending' | 'analyzing' | 'completed' | 'failed'
export type DownloadStatus = 'pending' | 'downloading' | 'completed' | 'failed' | 'skipped'

export interface LlmConfig {
  id: number
  name: string
  model_name: string
  api_endpoint: string
  api_key: string
  is_active: boolean
  created_at: string
}

export interface SystemPrompt {
  id: number
  name: string
  content: string
  version: string
  tags: string
  is_active: boolean
  creator_id: number
  creator_name: string
  ref_count: number
  created_at: string
  updated_at: string
}

export interface PromptTemplate {
  id: number
  name: string
  content: string
  version: string
  tags: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface SystemConfig {
  key: string
  value: string
  description: string
  updated_by: number
  updated_at: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
