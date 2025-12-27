import type { CustomMcp } from '@/types';
import { Button, Input, Label, Textarea, Switch } from '@/components/ui';
import { Plus, X } from 'lucide-react';
import { BaseModal } from '@/components/ui/shared/BaseModal';
import { useState, useEffect, useRef } from 'react';

interface EnvVarEntry {
  id: string;
  key: string;
  value: string;
}

interface McpDialogProps {
  isOpen: boolean;
  isEditing: boolean;
  mcp: CustomMcp;
  error: string | null;
  onClose: () => void;
  onSubmit: () => void;
  onMcpChange: <K extends keyof CustomMcp>(field: K, value: CustomMcp[K]) => void;
}

export const McpDialog: React.FC<McpDialogProps> = ({
  isOpen,
  isEditing,
  mcp,
  error,
  onClose,
  onSubmit,
  onMcpChange,
}) => {
  const [envVarEntries, setEnvVarEntries] = useState<EnvVarEntry[]>([]);
  const idCounterRef = useRef(0);

  const generateId = () => {
    idCounterRef.current += 1;
    return `entry-${idCounterRef.current}`;
  };

  useEffect(() => {
    if (!isOpen) return;
    idCounterRef.current = 0;
    const entries = Object.entries(mcp.env_vars || {}).map(([key, value]) => ({
      id: generateId(),
      key,
      value,
    }));
    setEnvVarEntries(entries);
    // We intentionally omit mcp.env_vars from deps - we only want to initialize
    // when dialog opens, not when parent state updates (which we trigger ourselves)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const syncEnvVarsToParent = (entries: EnvVarEntry[]) => {
    const envVars: Record<string, string> = {};
    entries.forEach((entry) => {
      if (entry.key) {
        envVars[entry.key] = entry.value;
      }
    });
    onMcpChange('env_vars', Object.keys(envVars).length > 0 ? envVars : undefined);
  };

  const addEnvVar = () => {
    const newEntries = [...envVarEntries, { id: generateId(), key: '', value: '' }];
    setEnvVarEntries(newEntries);
    syncEnvVarsToParent(newEntries);
  };

  const updateEnvVar = (id: string, key: string, value: string) => {
    const newEntries = envVarEntries.map((entry) =>
      entry.id === id ? { ...entry, key, value } : entry,
    );
    setEnvVarEntries(newEntries);
    syncEnvVarsToParent(newEntries);
  };

  const removeEnvVar = (id: string) => {
    const newEntries = envVarEntries.filter((entry) => entry.id !== id);
    setEnvVarEntries(newEntries);
    syncEnvVarsToParent(newEntries);
  };

  const addArg = () => {
    onMcpChange('args', [...(mcp.args || []), '']);
  };

  const updateArg = (index: number, value: string) => {
    const args = [...(mcp.args || [])];
    args[index] = value;
    onMcpChange('args', args);
  };

  const removeArg = (index: number) => {
    const args = [...(mcp.args || [])];
    args.splice(index, 1);
    onMcpChange('args', args.length > 0 ? args : undefined);
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      size="2xl"
      className="max-h-[90vh] overflow-y-auto shadow-strong"
    >
      <div className="p-6">
        <h3 className="mb-4 text-lg font-semibold text-text-primary dark:text-text-dark-primary">
          {isEditing ? 'Edit MCP Server' : 'Add New MCP Server'}
        </h3>

        {error && (
          <div className="mb-4 rounded-md border border-error-200 bg-error-50 p-3 dark:border-error-800 dark:bg-error-900/20">
            <p className="text-xs text-error-700 dark:text-error-400">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
              MCP Server Name
            </Label>
            <Input
              value={mcp.name}
              onChange={(e) => onMcpChange('name', e.target.value)}
              placeholder="e.g., google-maps, netlify, stripe"
              className="text-sm"
            />
            <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              A unique identifier for this MCP server (use lowercase with hyphens)
            </p>
          </div>

          <div>
            <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
              Description
            </Label>
            <Textarea
              value={mcp.description}
              onChange={(e) => onMcpChange('description', e.target.value)}
              placeholder="What does this MCP server do?"
              rows={3}
              className="text-sm"
            />
            <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              A brief description of the MCP server's purpose and capabilities
            </p>
          </div>

          <div>
            <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
              Command Type
            </Label>
            <select
              value={mcp.command_type}
              onChange={(e) =>
                onMcpChange('command_type', e.target.value as 'npx' | 'bunx' | 'uvx' | 'http')
              }
              className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-2 focus:ring-brand-500 dark:border-border-dark dark:bg-surface-dark dark:text-text-dark-primary"
            >
              <option value="npx">NPX Package</option>
              <option value="bunx">Bunx Package</option>
              <option value="uvx">uvx Package</option>
              <option value="http">HTTP Endpoint</option>
            </select>
            <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              The type of MCP server to run
            </p>
          </div>

          {(mcp.command_type === 'npx' ||
            mcp.command_type === 'bunx' ||
            mcp.command_type === 'uvx') && (
            <div>
              <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
                {mcp.command_type === 'npx'
                  ? 'NPM Package'
                  : mcp.command_type === 'bunx'
                    ? 'Bun Package'
                    : 'Python Package'}
              </Label>
              <Input
                value={mcp.package || ''}
                onChange={(e) => onMcpChange('package', e.target.value)}
                placeholder="e.g., @netlify/mcp, @stripe/mcp-server"
                className="font-mono text-sm"
              />
              <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                The package name to run with {mcp.command_type}
              </p>
            </div>
          )}

          {mcp.command_type === 'http' && (
            <div>
              <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
                HTTP URL
              </Label>
              <Input
                value={mcp.url || ''}
                onChange={(e) => onMcpChange('url', e.target.value)}
                placeholder="e.g., https://api.example.com/mcp"
                className="font-mono text-sm"
              />
              <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                The HTTP endpoint URL for the MCP server
              </p>
            </div>
          )}

          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label className="text-sm text-text-primary dark:text-text-dark-primary">
                Environment Variables
              </Label>
              <Button
                type="button"
                onClick={addEnvVar}
                variant="ghost"
                size="sm"
                className="flex items-center gap-1 text-xs"
              >
                <Plus className="h-3 w-3" />
                Add Variable
              </Button>
            </div>
            <div className="space-y-2">
              {envVarEntries.map((entry) => (
                <div key={entry.id} className="flex gap-2">
                  <Input
                    value={entry.key}
                    onChange={(e) => updateEnvVar(entry.id, e.target.value, entry.value)}
                    placeholder="KEY"
                    className="flex-1 font-mono text-xs"
                  />
                  <Input
                    value={entry.value}
                    onChange={(e) => updateEnvVar(entry.id, entry.key, e.target.value)}
                    placeholder="value"
                    className="flex-1 font-mono text-xs"
                  />
                  <Button
                    type="button"
                    onClick={() => removeEnvVar(entry.id)}
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 flex-shrink-0"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              {envVarEntries.length === 0 && (
                <p className="text-xs italic text-text-tertiary dark:text-text-dark-tertiary">
                  No environment variables configured
                </p>
              )}
            </div>
            <p className="mt-1.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              {mcp.command_type === 'http'
                ? 'HTTP headers (e.g., Authorization)'
                : 'Environment variables passed to the MCP server'}
            </p>
          </div>

          <div>
            <div className="mb-2 flex items-center justify-between">
              <Label className="text-sm text-text-primary dark:text-text-dark-primary">
                Additional Arguments
              </Label>
              <Button
                type="button"
                onClick={addArg}
                variant="ghost"
                size="sm"
                className="flex items-center gap-1 text-xs"
              >
                <Plus className="h-3 w-3" />
                Add Argument
              </Button>
            </div>
            <div className="space-y-2">
              {(mcp.args || []).map((arg, index) => (
                <div key={index} className="flex gap-2">
                  <Input
                    value={arg}
                    onChange={(e) => updateArg(index, e.target.value)}
                    placeholder="--flag or value"
                    className="flex-1 font-mono text-xs"
                  />
                  <Button
                    type="button"
                    onClick={() => removeArg(index)}
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 flex-shrink-0"
                  >
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
              {(!mcp.args || mcp.args.length === 0) && (
                <p className="text-xs italic text-text-tertiary dark:text-text-dark-tertiary">
                  No additional arguments configured
                </p>
              )}
            </div>
            <p className="mt-1.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              Optional command-line arguments passed to the MCP server
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-sm text-text-primary dark:text-text-dark-primary">
                Enable MCP Server
              </Label>
              <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                MCP server will only be available when enabled
              </p>
            </div>
            <Switch
              checked={mcp.enabled ?? true}
              onCheckedChange={(checked) => onMcpChange('enabled', checked)}
              size="sm"
              aria-label="Enable MCP server"
            />
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" onClick={onClose} variant="outline" size="sm">
            Cancel
          </Button>
          <Button type="button" onClick={onSubmit} variant="primary" size="sm">
            {isEditing ? 'Update MCP Server' : 'Add MCP Server'}
          </Button>
        </div>
      </div>
    </BaseModal>
  );
};
