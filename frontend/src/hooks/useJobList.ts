import { useQuery } from '@tanstack/react-query';
import { listJobs } from '../api/jobs';
import type { JobSummary } from '../api/types';

export function useJobList() {
  return useQuery({
    queryKey: ['jobs'],
    queryFn: () => listJobs({ limit: 50 }),
    refetchInterval: (query) => {
      const jobs: JobSummary[] = query.state.data?.jobs ?? [];
      const hasActive = jobs.some(
        (j) => j.status === 'queued' || j.status === 'running',
      );
      return hasActive ? 3000 : 10000;
    },
    staleTime: 2000,
  });
}
