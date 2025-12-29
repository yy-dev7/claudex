import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui';

interface NoOpenPortsStateProps {
  onRefresh: () => void;
  loading?: boolean;
}

export const NoOpenPortsState = ({ onRefresh, loading = false }: NoOpenPortsStateProps) => {
  return (
    <div className="flex h-full flex-col items-center justify-center text-text-tertiary dark:text-text-dark-tertiary">
      <p className="mb-2 text-xs">No open ports detected</p>
      <Button
        onClick={onRefresh}
        disabled={loading}
        variant="unstyled"
        className="flex items-center gap-1.5 rounded-md bg-surface-secondary px-2.5 py-1 text-xs transition-colors hover:bg-surface-tertiary dark:bg-surface-dark-secondary dark:hover:bg-surface-dark-tertiary"
      >
        <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
        <span>Refresh</span>
      </Button>
    </div>
  );
};
