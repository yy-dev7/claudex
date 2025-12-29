import { useState, useEffect, useCallback } from 'react';
import QRCode from 'qrcode';
import { Smartphone, RefreshCw } from 'lucide-react';
import { Button, Select, Spinner } from '@/components/ui';
import { usePreviewLinksQuery } from '@/hooks/queries';
import { NoOpenPortsState } from '../shared/NoOpenPortsState';

export interface MobilePreviewProps {
  sandboxId?: string;
}

export const MobilePreview = ({ sandboxId }: MobilePreviewProps) => {
  const [qrCode, setQrCode] = useState('');
  const [isLoadingQr, setIsLoadingQr] = useState(false);
  const [selectedPortId, setSelectedPortId] = useState<number | null>(null);
  const [iframeKey, setIframeKey] = useState(0);

  const {
    data: ports = [],
    isLoading: loadingPorts,
    refetch,
  } = usePreviewLinksQuery(sandboxId || '', {
    enabled: !!sandboxId,
  });

  const selectedPort =
    ports.length > 0 ? ports.find((p) => p.port === selectedPortId) || ports[0] : null;

  const previewUrl = selectedPort?.previewUrl || '';
  const expoUrl = previewUrl.replace(/^https?:\/\//, 'exp://');

  useEffect(() => {
    if (!previewUrl) return;

    setIsLoadingQr(true);
    QRCode.toDataURL(expoUrl, {
      width: 280,
      margin: 1,
      color: {
        dark: '#000000',
        light: '#FFFFFF',
      },
    })
      .then(setQrCode)
      .finally(() => setIsLoadingQr(false));
  }, [previewUrl, expoUrl]);

  const handleRefresh = useCallback(() => {
    setIframeKey((prev) => prev + 1);
    refetch();
  }, [refetch]);

  if (!sandboxId) {
    return (
      <div className="flex h-full items-center justify-center bg-surface text-text-tertiary dark:bg-surface-dark dark:text-text-dark-tertiary">
        <div className="text-center">
          <Smartphone className="mx-auto mb-3 h-12 w-12 opacity-40" />
          <p className="text-sm">No sandbox connected</p>
        </div>
      </div>
    );
  }

  if (ports.length === 0) {
    return <NoOpenPortsState onRefresh={handleRefresh} loading={loadingPorts} />;
  }

  return (
    <div className="flex h-full bg-surface dark:bg-surface-dark">
      <div className="relative flex flex-1 items-center justify-center p-8">
        {ports.length > 0 && (
          <div className="absolute right-4 top-4 flex items-center gap-1.5 rounded-lg bg-surface-secondary px-2 py-1.5 dark:bg-surface-dark-secondary">
            <span className="text-xs text-text-tertiary dark:text-text-dark-tertiary">Port:</span>
            <Select
              value={selectedPort?.port?.toString() ?? ''}
              onChange={(e) => setSelectedPortId(Number(e.target.value))}
              className="h-6 border-border-secondary bg-surface text-xs dark:border-border-dark-secondary dark:bg-surface-dark-secondary"
            >
              {ports.map((p) => (
                <option key={p.port} value={p.port}>
                  {p.port}
                </option>
              ))}
            </Select>
            <Button
              onClick={handleRefresh}
              disabled={loadingPorts}
              variant="unstyled"
              className="rounded p-1 text-text-tertiary hover:text-text-secondary dark:hover:text-text-dark-secondary"
              title="Refresh"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingPorts ? 'animate-spin' : ''}`} />
            </Button>
          </div>
        )}

        <div className="relative">
          <div className="relative h-[700px] w-[340px] rounded-5xl border-[14px] border-surface-tertiary bg-surface-tertiary shadow-strong dark:border-surface-dark-secondary dark:bg-surface-dark-secondary">
            <div className="absolute left-1/2 top-0 z-10 h-8 w-32 -translate-x-1/2 rounded-b-3xl bg-surface dark:bg-surface-dark"></div>

            <div className="relative h-full w-full overflow-hidden rounded-4xl bg-white dark:bg-black">
              <iframe
                key={`${previewUrl}-${iframeKey}`}
                src={previewUrl}
                className="h-full w-full border-0"
                title="App Preview"
                sandbox="allow-scripts allow-same-origin allow-forms"
              />
            </div>
          </div>
        </div>
      </div>

      <div className="flex w-[420px] items-center justify-center border-l border-border p-8 dark:border-border-dark">
        <div className="w-full max-w-sm">
          <h3 className="mb-8 text-center text-xl font-semibold text-text-primary dark:text-white">
            Test on your phone
          </h3>

          <div className="mb-8 flex justify-center">
            <div className="inline-block rounded-2xl bg-white p-5 shadow-sm dark:shadow-none">
              {isLoadingQr ? (
                <div className="flex h-72 w-72 items-center justify-center">
                  <Spinner size="lg" className="text-brand-600" />
                </div>
              ) : qrCode ? (
                <img src={qrCode} alt="Expo QR Code" className="h-72 w-72" />
              ) : (
                <div className="flex h-72 w-72 items-center justify-center text-text-tertiary dark:text-text-dark-tertiary">
                  <p className="text-sm">QR code unavailable</p>
                </div>
              )}
            </div>
          </div>

          <div className="space-y-3 text-sm text-text-secondary dark:text-text-dark-secondary">
            <p className="text-center font-medium text-text-primary dark:text-text-dark-primary">
              Scan QR code to open
            </p>
            <ol className="list-inside list-decimal space-y-2 pl-1 text-xs">
              <li>Install Expo Go from App Store or Play Store</li>
              <li>Open Camera app</li>
              <li>Scan the QR code above</li>
            </ol>

            <div className="mt-4 border-t border-border pt-4 dark:border-border-dark">
              <p className="mb-2 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                Or enter this URL manually:
              </p>
              <div className="break-all rounded bg-surface-secondary p-3 font-mono text-xs text-text-secondary dark:bg-surface-dark-secondary dark:text-text-dark-secondary">
                {expoUrl}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
