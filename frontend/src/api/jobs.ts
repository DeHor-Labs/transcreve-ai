import { get, post, postForm } from './client';
import type {
  DossierResponse,
  JobDetail,
  JobListResponse,
  SubmitResponse,
  SubmitUrlPayload,
} from './types';

export function submitUrl(payload: SubmitUrlPayload): Promise<SubmitResponse> {
  return post<SubmitResponse>('/jobs', payload);
}

export function submitFile(
  file: File,
  opts: { language?: string; ai_mode?: string; provider?: string },
): Promise<SubmitResponse> {
  const form = new FormData();
  form.append('file', file);
  if (opts.language) form.append('language', opts.language);
  if (opts.ai_mode) form.append('ai_mode', opts.ai_mode);
  if (opts.provider) form.append('provider', opts.provider);
  return postForm<SubmitResponse>('/jobs', form);
}

export function listJobs(params?: {
  limit?: number;
  status?: string;
}): Promise<JobListResponse> {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set('limit', String(params.limit));
  if (params?.status) qs.set('status', params.status);
  const q = qs.toString();
  return get<JobListResponse>(`/jobs${q ? `?${q}` : ''}`);
}

export function getJob(jobId: string): Promise<JobDetail> {
  return get<JobDetail>(`/jobs/${jobId}`);
}

export function getDossier(jobId: string): Promise<DossierResponse> {
  return get<DossierResponse>(`/jobs/${jobId}/dossier`);
}

export function createEventSource(jobId: string): EventSource {
  return new EventSource(`/api/jobs/${jobId}/events`);
}
