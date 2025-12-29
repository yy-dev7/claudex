import { Button, ListManagementTab } from '@/components/ui';
import type { CustomEnvVar } from '@/types';
import { Key, Eye, EyeOff } from 'lucide-react';
import { useState } from 'react';

interface EnvVarsSettingsTabProps {
  envVars: CustomEnvVar[] | null;
  onAddEnvVar: () => void;
  onEditEnvVar: (index: number) => void;
  onDeleteEnvVar: (index: number) => void | Promise<void>;
}

const maskValue = (value: string) => {
  if (value.length <= 4) return '••••';
  return `${value.slice(0, 4)}${'•'.repeat(Math.min(value.length - 4, 20))}`;
};

export const EnvVarsSettingsTab: React.FC<EnvVarsSettingsTabProps> = ({
  envVars,
  onAddEnvVar,
  onEditEnvVar,
  onDeleteEnvVar,
}) => {
  const [revealedValues, setRevealedValues] = useState<Record<string, boolean>>({});

  const toggleValueVisibility = (key: string) => {
    setRevealedValues((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleDelete = async (index: number) => {
    const deletedKey = envVars?.[index]?.key;
    await onDeleteEnvVar(index);
    if (deletedKey) {
      setRevealedValues((prev) => {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const { [deletedKey]: _, ...rest } = prev;
        return rest;
      });
    }
  };

  return (
    <ListManagementTab<CustomEnvVar>
      title="Environment Variables"
      description="Configure environment variables that will be available in every sandbox. Perfect for API keys like OPENAI_API_KEY, GEMINI_API_KEY, etc."
      items={envVars}
      emptyIcon={Key}
      emptyText="No custom environment variables configured yet"
      emptyButtonText="Add Your First Environment Variable"
      addButtonText="Add Environment Variable"
      deleteConfirmTitle="Delete Environment Variable"
      deleteConfirmMessage={(envVar) =>
        `Are you sure you want to delete "${envVar.key}"? This action cannot be undone.`
      }
      getItemKey={(envVar) => envVar.key}
      onAdd={onAddEnvVar}
      onEdit={onEditEnvVar}
      onDelete={handleDelete}
      renderItem={(envVar) => (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Key className="h-4 w-4 flex-shrink-0 text-brand-600 dark:text-brand-400" />
            <h3 className="min-w-0 max-w-full truncate font-mono text-sm font-medium text-text-primary dark:text-text-dark-primary">
              {envVar.key}
            </h3>
          </div>
          <div className="rounded bg-surface-secondary p-2 dark:bg-surface-dark-secondary">
            <div className="flex items-center justify-between gap-2">
              <p className="break-all font-mono text-xs text-text-secondary dark:text-text-dark-secondary">
                {revealedValues[envVar.key] ? envVar.value : maskValue(envVar.value)}
              </p>
              <Button
                type="button"
                onClick={() => toggleValueVisibility(envVar.key)}
                variant="ghost"
                size="icon"
                className="h-6 w-6 flex-shrink-0 text-text-tertiary hover:text-text-secondary dark:text-text-dark-tertiary dark:hover:text-text-dark-secondary"
                aria-label={
                  revealedValues[envVar.key]
                    ? `Hide ${envVar.key} value`
                    : `Show ${envVar.key} value`
                }
              >
                {revealedValues[envVar.key] ? (
                  <EyeOff className="h-3.5 w-3.5" />
                ) : (
                  <Eye className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          </div>
        </>
      )}
      logContext="EnvVarsSettingsTab"
    />
  );
};
