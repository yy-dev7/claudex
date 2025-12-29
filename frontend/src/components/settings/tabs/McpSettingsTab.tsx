import { Switch, ListManagementTab } from '@/components/ui';
import type { CustomMcp } from '@/types';
import { Plug } from 'lucide-react';

interface McpSettingsTabProps {
  mcps: CustomMcp[] | null;
  onAddMcp: () => void;
  onEditMcp: (index: number) => void;
  onDeleteMcp: (index: number) => void | Promise<void>;
  onToggleMcp: (index: number, enabled: boolean) => void;
}

const getCommandTypeBadge = (commandType: string): string => {
  switch (commandType) {
    case 'npx':
      return 'NPX';
    case 'bunx':
      return 'Bunx';
    case 'uvx':
      return 'uvx';
    case 'http':
      return 'HTTP';
    default:
      return commandType.toUpperCase();
  }
};

const getCommandTypeColor = (commandType: string): string => {
  switch (commandType) {
    case 'npx':
      return 'bg-info-100 dark:bg-info-900/30 text-info-700 dark:text-info-300';
    case 'bunx':
      return 'bg-warning-100 dark:bg-warning-900/30 text-warning-700 dark:text-warning-300';
    case 'uvx':
      return 'bg-success-100 dark:bg-success-900/30 text-success-700 dark:text-success-300';
    case 'http':
      return 'bg-brand-100 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300';
    default:
      return 'bg-text-quaternary/10 dark:bg-text-dark-quaternary/10 text-text-secondary dark:text-text-dark-secondary';
  }
};

export const McpSettingsTab: React.FC<McpSettingsTabProps> = ({
  mcps,
  onAddMcp,
  onEditMcp,
  onDeleteMcp,
  onToggleMcp,
}) => {
  return (
    <ListManagementTab<CustomMcp>
      title="Custom MCP Servers"
      description="Configure custom Model Context Protocol (MCP) servers to extend Claude's capabilities. MCP servers can provide tools, resources, and prompts for specialized tasks."
      items={mcps}
      emptyIcon={Plug}
      emptyText="No custom MCP servers configured yet"
      emptyButtonText="Add Your First MCP Server"
      addButtonText="Add MCP Server"
      deleteConfirmTitle="Delete MCP Server"
      deleteConfirmMessage={(mcp) =>
        `Are you sure you want to delete "${mcp.name}"? This action cannot be undone.`
      }
      getItemKey={(mcp) => mcp.name}
      onAdd={onAddMcp}
      onEdit={onEditMcp}
      onDelete={onDeleteMcp}
      renderItem={(mcp, index) => (
        <>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Plug className="h-4 w-4 flex-shrink-0 text-brand-600 dark:text-brand-400" />
            <h3 className="min-w-0 max-w-full truncate text-sm font-medium text-text-primary dark:text-text-dark-primary sm:max-w-[250px]">
              {mcp.name}
            </h3>
            <span
              className={`shrink-0 rounded px-2 py-0.5 text-xs font-medium ${getCommandTypeColor(mcp.command_type)}`}
            >
              {getCommandTypeBadge(mcp.command_type)}
            </span>
            <Switch
              checked={mcp.enabled ?? true}
              onCheckedChange={(checked) => onToggleMcp(index, checked)}
              size="sm"
              aria-label={`Toggle ${mcp.name} MCP server`}
            />
          </div>
          <p className="mb-2 text-xs text-text-tertiary dark:text-text-dark-tertiary">
            {mcp.description}
          </p>
          <div className="mt-2 rounded bg-surface-secondary p-2 dark:bg-surface-dark-secondary">
            <div className="space-y-1">
              {(mcp.command_type === 'npx' ||
                mcp.command_type === 'bunx' ||
                mcp.command_type === 'uvx') &&
                mcp.package && (
                  <p className="font-mono text-xs text-text-secondary dark:text-text-dark-secondary">
                    <span className="text-text-tertiary dark:text-text-dark-tertiary">
                      Package:
                    </span>{' '}
                    {mcp.package}
                  </p>
                )}
              {mcp.command_type === 'http' && mcp.url && (
                <p className="font-mono text-xs text-text-secondary dark:text-text-dark-secondary">
                  <span className="text-text-tertiary dark:text-text-dark-tertiary">URL:</span>{' '}
                  {mcp.url}
                </p>
              )}
              {mcp.env_vars && Object.keys(mcp.env_vars).length > 0 && (
                <p className="text-xs text-text-tertiary dark:text-text-dark-tertiary">
                  {Object.keys(mcp.env_vars).length} environment variable(s) configured
                </p>
              )}
            </div>
          </div>
        </>
      )}
      logContext="McpSettingsTab"
    />
  );
};
