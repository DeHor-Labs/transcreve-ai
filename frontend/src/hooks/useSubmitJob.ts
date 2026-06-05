import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { submitFile, submitUrl } from '../api/jobs';
import type { SubmitUrlPayload } from '../api/types';

interface SubmitUrlArgs {
  type: 'url';
  payload: SubmitUrlPayload;
}

interface SubmitFileArgs {
  type: 'file';
  file: File;
  opts: { language?: string; ai_mode?: string; provider?: string };
}

type SubmitArgs = SubmitUrlArgs | SubmitFileArgs;

export function useSubmitJob() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (args: SubmitArgs) => {
      if (args.type === 'url') {
        return submitUrl(args.payload);
      }
      return submitFile(args.file, args.opts);
    },
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      navigate(`/jobs/${data.job_id}`);
    },
  });
}
