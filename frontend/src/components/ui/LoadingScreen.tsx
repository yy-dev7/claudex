import { Loader2 } from 'lucide-react';

export function LoadingScreen() {
  return (
    <div className="min-h-viewport flex items-center justify-center bg-surface-dark">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-brand-400" />
        <p className="text-text-dark-quaternary">Loading...</p>
      </div>
    </div>
  );
}
