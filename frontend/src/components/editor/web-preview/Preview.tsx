import { memo, useState, useCallback } from 'react';
import { Panel } from './Panel';
import type { PortInfo } from '@/types';
import { usePreviewLinksQuery } from '@/hooks/queries';
import { NoOpenPortsState } from '../shared/NoOpenPortsState';

export interface WebPreviewProps {
  sandboxId?: string;
  isActive?: boolean;
}

export const WebPreview = memo(function WebPreview({
  sandboxId,
  isActive = false,
}: WebPreviewProps) {
  const [selectedPortId, setSelectedPortId] = useState<number | null>(null);

  const {
    data: ports = [],
    isLoading: loading,
    refetch,
  } = usePreviewLinksQuery(sandboxId || '', {
    enabled: !!sandboxId && isActive,
  });

  const fetchPorts = useCallback(() => {
    refetch();
  }, [refetch]);

  const selectedPort =
    ports.length > 0 ? ports.find((p) => p.port === selectedPortId) || ports[0] : null;

  const setSelectedPort = useCallback((port: PortInfo | null) => {
    setSelectedPortId(port?.port || null);
  }, []);

  return (
    <div className="flex h-full flex-col">
      {!sandboxId ? (
        <div className="flex h-full items-center justify-center text-xs text-text-tertiary dark:text-text-dark-tertiary">
          No sandbox connected
        </div>
      ) : ports.length === 0 ? (
        <NoOpenPortsState onRefresh={fetchPorts} loading={loading} />
      ) : (
        <div className="flex h-full flex-1">
          <Panel
            previewUrl={selectedPort?.previewUrl}
            ports={ports}
            selectedPort={selectedPort}
            onPortChange={setSelectedPort}
            onRefreshPorts={fetchPorts}
          />
        </div>
      )}
    </div>
  );
});
