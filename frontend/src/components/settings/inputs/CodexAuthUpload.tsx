import { useState, useRef, useCallback } from 'react';
import { Upload, X, Check, FileJson } from 'lucide-react';
import { Button } from '@/components/ui';

interface CodexAuthUploadProps {
  value: string | null;
  onChange: (content: string | null) => void;
}

interface CodexAuthTokens {
  access_token?: string;
  refresh_token?: string;
}

interface CodexAuthJson {
  tokens?: CodexAuthTokens;
}

const validateCodexAuth = (content: string): string | null => {
  let parsed: CodexAuthJson;
  try {
    parsed = JSON.parse(content);
  } catch {
    return 'Invalid JSON file';
  }

  if (!parsed.tokens) {
    return 'Missing "tokens" object';
  }

  if (!parsed.tokens.access_token) {
    return 'Missing "tokens.access_token"';
  }

  if (!parsed.tokens.refresh_token) {
    return 'Missing "tokens.refresh_token"';
  }

  return null;
};

export const CodexAuthUpload: React.FC<CodexAuthUploadProps> = ({ value, onChange }) => {
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileRead = useCallback(
    (file: File) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        const validationError = validateCodexAuth(content);
        if (validationError) {
          setError(validationError);
          return;
        }
        setError(null);
        onChange(content);
      };
      reader.onerror = () => setError('Failed to read file');
      reader.readAsText(file);
    },
    [onChange],
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFileRead(file);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file?.name.endsWith('.json')) {
      handleFileRead(file);
    } else {
      setError('Please upload a .json file');
    }
  };

  const handleRemove = () => {
    onChange(null);
    setError(null);
  };

  return (
    <div className="mt-2 space-y-2">
      {value ? (
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface-secondary p-3 dark:border-border-dark dark:bg-surface-dark-secondary">
          <div className="flex items-center gap-2">
            <Check className="h-4 w-4 text-success-600" />
            <span className="text-sm text-text-primary dark:text-text-dark-primary">
              auth.json configured
            </span>
          </div>
          <Button variant="ghost" size="sm" onClick={handleRemove}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <div
          className={`rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
            isDragging
              ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/10'
              : 'border-border dark:border-border-dark'
          }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <FileJson className="mx-auto mb-2 h-8 w-8 text-text-quaternary dark:text-text-dark-quaternary" />
          <div className="flex items-center justify-center gap-1">
            <Upload className="h-3.5 w-3.5 text-text-tertiary dark:text-text-dark-tertiary" />
            <p className="text-xs text-text-secondary dark:text-text-dark-secondary">
              Drop auth.json here or{' '}
              <label className="cursor-pointer text-brand-600 hover:underline dark:text-brand-400">
                browse
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".json"
                  onChange={handleFileChange}
                  className="hidden"
                />
              </label>
            </p>
          </div>
        </div>
      )}
      {error && <p className="text-xs text-error-600 dark:text-error-400">{error}</p>}
    </div>
  );
};
