export interface ProgressEvent {
  step: string;
  detail: string;
  pct: number;
  status: 'running' | 'completed' | 'failed';
  ts: string;
}

export interface JobSummary {
  job_id: string;
  title: string;
  source: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  created_at: string;
  finished_at: string | null;
  duration_seconds: number | null;
  provider: string;
  ai_mode: string;
  warnings_count: number;
  storage_backend: string;
  progress: ProgressEvent | null;
}

export interface JobDetail extends JobSummary {
  output_dir: string | null;
  analysis_path: string | null;
  markdown_path: string | null;
  source_hash: string | null;
  progress_history: ProgressEvent[];
}

export interface DossierAnalysis {
  run_id?: string;
  created_at?: string;
  source?: string;
  metadata: {
    title: string;
    uploader: string;
    channel: string;
    duration: number;
    upload_date: string;
    description: string;
    webpage_url: string;
  };
  synthesis: {
    summary: string;
    chapters: Array<{ title: string; start: number; end: number }>;
    entities: string[];
    tools_or_products: string[];
    claims: string[];
    action_items: string[];
    questions: string[];
    raw?: Record<string, unknown>;
  };
  transcript_text: string;
  frames_count: number;
  warnings: string[];
}

export interface DossierResponse {
  job_id: string;
  markdown: string;
  analysis: DossierAnalysis;
}

export interface JobListResponse {
  jobs: JobSummary[];
  total: number;
}

export interface SubmitResponse {
  job_id: string;
  status: string;
  queued_at: string;
}

export interface SubmitUrlPayload {
  source: string;
  language?: string;
  ai_mode?: 'auto' | 'off' | 'full';
  provider?: 'openai' | 'gemini' | 'anthropic' | 'local';
}

export interface ApiError {
  error: string;
  message: string;
  existing_run_id?: string;
}
