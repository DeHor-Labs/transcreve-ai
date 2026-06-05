import { useQuery } from '@tanstack/react-query';
import { getJob } from '../api/jobs';

export function useJobDetail(jobId: string) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'completed' || status === 'failed') return false;
      return 4000;
    },
    staleTime: 1000,
  });
}
