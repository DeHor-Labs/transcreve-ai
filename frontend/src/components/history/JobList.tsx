import type { JobSummary } from '../../api/types';
import { EmptyState } from '../ui/EmptyState';
import { JobCard } from './JobCard';

interface JobListProps {
  jobs: JobSummary[];
}

export function JobList({ jobs }: JobListProps) {
  if (jobs.length === 0) {
    return (
      <EmptyState
        title="Nenhuma analise ainda"
        message="Submeta um link ou arquivo acima para comecar."
      />
    );
  }

  return (
    <div className="flex flex-col gap-2 animate-stagger">
      {jobs.map((job) => (
        <JobCard key={job.job_id} job={job} />
      ))}
    </div>
  );
}
