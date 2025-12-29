import { Switch, ListManagementTab } from '@/components/ui';
import type { CustomAgent } from '@/types';
import { Bot } from 'lucide-react';

interface AgentsSettingsTabProps {
  agents: CustomAgent[] | null;
  onAddAgent: () => void;
  onEditAgent: (index: number) => void;
  onDeleteAgent: (index: number) => void | Promise<void>;
  onToggleAgent: (index: number, enabled: boolean) => void;
}

export const AgentsSettingsTab: React.FC<AgentsSettingsTabProps> = ({
  agents,
  onAddAgent,
  onEditAgent,
  onDeleteAgent,
  onToggleAgent,
}) => {
  return (
    <ListManagementTab<CustomAgent>
      title="Custom Agents"
      description="Create custom AI agents with specific instructions and behaviors. Agents can be invoked during conversations to handle specialized tasks."
      items={agents}
      emptyIcon={Bot}
      emptyText="No custom agents configured yet"
      emptyButtonText="Create Your First Agent"
      addButtonText="Add Agent"
      deleteConfirmTitle="Delete Agent"
      deleteConfirmMessage={(agent) =>
        `Are you sure you want to delete "${agent.name}"? This action cannot be undone.`
      }
      getItemKey={(agent) => agent.name}
      onAdd={onAddAgent}
      onEdit={onEditAgent}
      onDelete={onDeleteAgent}
      renderItem={(agent, index) => (
        <>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Bot className="h-4 w-4 flex-shrink-0 text-brand-600 dark:text-brand-400" />
            <h3 className="min-w-0 max-w-full truncate text-sm font-medium text-text-primary dark:text-text-dark-primary sm:max-w-[250px]">
              {agent.name}
            </h3>
            <Switch
              checked={agent.enabled ?? true}
              onCheckedChange={(checked) => onToggleAgent(index, checked)}
              size="sm"
              aria-label={`Toggle ${agent.name} agent`}
            />
          </div>
          <p className="mb-2 line-clamp-2 text-xs text-text-tertiary dark:text-text-dark-tertiary">
            {agent.description}
          </p>
          <div className="mt-2 rounded bg-surface-secondary p-2 dark:bg-surface-dark-secondary">
            <p className="line-clamp-2 font-mono text-xs text-text-secondary dark:text-text-dark-secondary">
              {agent.content}
            </p>
          </div>
        </>
      )}
      logContext="AgentsSettingsTab"
    />
  );
};
