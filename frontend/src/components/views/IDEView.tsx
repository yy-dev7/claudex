import { memo, useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { Download, ExternalLink, RotateCcw } from 'lucide-react';
import { Button, Spinner } from '@/components/ui';
import { useIDEUrlQuery } from '@/hooks/queries';
import { useUIStore } from '@/store';
import { sandboxService } from '@/services/sandboxService';

interface IDEViewProps {
  sandboxId?: string;
  isActive?: boolean;
}

export const IDEView = memo(function IDEView({ sandboxId, isActive = false }: IDEViewProps) {
  const theme = useUIStore((state) => state.theme);
  const [isLoading, setIsLoading] = useState(true);
  const [isDownloading, setIsDownloading] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const prevThemeRef = useRef(theme);
  const hasLoadedRef = useRef(false);

  const { data: ideUrl, isError, isFetched } = useIDEUrlQuery(sandboxId || '');

  const iframeKey = useMemo(() => {
    if (!ideUrl) return 'no-ide';
    return `${ideUrl}-${reloadToken}`;
  }, [ideUrl, reloadToken]);

  const handleLoad = useCallback(() => {
    setIsLoading(false);
    hasLoadedRef.current = true;
  }, []);

  const handleReload = useCallback(() => {
    setIsLoading(true);
    setReloadToken((t) => t + 1);
  }, []);

  const handleOpenInNewTab = useCallback(() => {
    if (ideUrl) {
      window.open(ideUrl, '_blank');
    }
  }, [ideUrl]);

  const handleDownload = useCallback(async () => {
    if (!sandboxId || isDownloading) return;

    setIsDownloading(true);
    try {
      const blob = await sandboxService.downloadZip(sandboxId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sandbox_${sandboxId}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      // Silently fail
    } finally {
      setIsDownloading(false);
    }
  }, [sandboxId, isDownloading]);

  useEffect(() => {
    if (!sandboxId || !hasLoadedRef.current) return;
    if (prevThemeRef.current === theme) return;

    prevThemeRef.current = theme;

    const updateTheme = async () => {
      try {
        await sandboxService.updateIDETheme(sandboxId, theme);
        handleReload();
      } catch {
        // Silently fail - theme sync is best effort
      }
    };

    updateTheme();
  }, [theme, sandboxId, handleReload]);

  useEffect(() => {
    if (isError || (isFetched && !ideUrl)) {
      setIsLoading(false);
    }
  }, [ideUrl, isError, isFetched]);

  if (!sandboxId) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-text-tertiary dark:text-text-dark-tertiary">
        No sandbox connected
      </div>
    );
  }

  if (!isActive) {
    return null;
  }

  return (
    <div className="flex h-full w-full flex-col bg-white dark:bg-surface-dark">
      <div className="flex items-center border-b border-border px-3 py-1.5 dark:border-white/10">
        <div className="flex flex-1 items-center gap-3">
          <Button
            onClick={handleReload}
            variant="unstyled"
            className="rounded-md bg-transparent p-1 text-text-tertiary transition-all hover:bg-surface-secondary hover:text-text-primary dark:text-text-dark-tertiary dark:hover:bg-surface-dark-secondary dark:hover:text-text-dark-primary"
            title="Reload IDE"
          >
            <RotateCcw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>

          <span className="text-xs font-medium text-text-secondary dark:text-text-dark-secondary">
            OpenVSCode Server
          </span>

          <div className="flex-1" />

          <Button
            onClick={handleDownload}
            variant="unstyled"
            className="rounded-md bg-transparent p-1 text-text-tertiary transition-all hover:bg-surface-secondary hover:text-text-primary disabled:cursor-wait disabled:opacity-50 dark:text-text-dark-tertiary dark:hover:bg-surface-dark-secondary dark:hover:text-text-dark-primary"
            title="Download all files"
            disabled={isDownloading}
          >
            <Download className={`h-3.5 w-3.5 ${isDownloading ? 'animate-pulse' : ''}`} />
          </Button>

          <Button
            onClick={handleOpenInNewTab}
            variant="unstyled"
            className="rounded-md bg-transparent p-1 text-text-tertiary transition-all hover:bg-surface-secondary hover:text-text-primary dark:text-text-dark-tertiary dark:hover:bg-surface-dark-secondary dark:hover:text-text-dark-primary"
            title="Open in new tab"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="relative flex-1 overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-white/50 dark:bg-black/50">
            <Spinner size="md" className="h-6 w-6 text-brand-500" />
          </div>
        )}
        <iframe
          key={iframeKey}
          src={ideUrl || undefined}
          className="h-full w-full border-0"
          title="OpenVSCode IDE"
          allow="clipboard-read; clipboard-write"
          onLoad={handleLoad}
        />
      </div>
    </div>
  );
});
