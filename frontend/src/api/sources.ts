import { post } from './client';
import type { SourceProbeResponse } from './types';

export interface SourceProbeRequest {
  source: string;
}

export function probeSource(payload: SourceProbeRequest): Promise<SourceProbeResponse> {
  return post<SourceProbeResponse>('/sources/probe', payload);
}
