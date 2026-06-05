import { post } from './client';

export interface SearchResult {
  run_id: string;
  title: string;
  source_url: string;
  chunk_type: string;
  excerpt: string;
  score: number;
  chapter_start: number | null;
}

export interface SearchResponse {
  query: string;
  total: number;
  results: SearchResult[];
}

export interface AskResponse {
  question: string;
  answer: string;
  sources: SearchResult[];
}

export function searchKnowledge(
  query: string,
  top_k = 5,
  run_ids?: string[],
): Promise<SearchResponse> {
  return post<SearchResponse>('/search', { query, top_k, run_ids: run_ids ?? null });
}

export function askKnowledge(
  question: string,
  top_k = 5,
  run_ids?: string[],
): Promise<AskResponse> {
  return post<AskResponse>('/ask', { question, top_k, run_ids: run_ids ?? null });
}
