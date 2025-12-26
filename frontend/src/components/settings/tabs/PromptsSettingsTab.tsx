import { ListManagementTab } from '@/components/ui';
import type { CustomPrompt } from '@/types';
import { FileText } from 'lucide-react';

interface PromptsSettingsTabProps {
  prompts: CustomPrompt[] | null;
  onAddPrompt: () => void;
  onEditPrompt: (index: number) => void;
  onDeletePrompt: (index: number) => void | Promise<void>;
}

export const PromptsSettingsTab: React.FC<PromptsSettingsTabProps> = ({
  prompts,
  onAddPrompt,
  onEditPrompt,
  onDeletePrompt,
}) => {
  return (
    <ListManagementTab<CustomPrompt>
      title="Prompts"
      description="Create custom system prompts. Use @prompt:name to select when chatting."
      items={prompts}
      emptyIcon={FileText}
      emptyText="No custom prompts configured yet"
      emptyButtonText="Create Your First Prompt"
      addButtonText="Add Prompt"
      deleteConfirmTitle="Delete Prompt"
      deleteConfirmMessage={(prompt) =>
        `Are you sure you want to delete "${prompt.name}"? This action cannot be undone.`
      }
      getItemKey={(prompt) => prompt.name}
      onAdd={onAddPrompt}
      onEdit={onEditPrompt}
      onDelete={onDeletePrompt}
      renderItem={(prompt) => (
        <>
          <div className="mb-1 flex items-center gap-2">
            <FileText className="h-4 w-4 flex-shrink-0 text-brand-600 dark:text-brand-400" />
            <h3 className="truncate text-sm font-medium text-text-primary dark:text-text-dark-primary">
              {prompt.name}
            </h3>
          </div>
          <div className="mt-2 rounded bg-surface-secondary p-2 dark:bg-surface-dark-secondary">
            <p className="line-clamp-3 font-mono text-xs text-text-secondary dark:text-text-dark-secondary">
              {prompt.content}
            </p>
          </div>
        </>
      )}
      logContext="PromptsSettingsTab"
    />
  );
};
