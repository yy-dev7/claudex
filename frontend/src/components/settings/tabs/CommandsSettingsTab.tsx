import { Switch, ListManagementTab } from '@/components/ui';
import type { CustomCommand } from '@/types';
import { Terminal } from 'lucide-react';

interface CommandsSettingsTabProps {
  commands: CustomCommand[] | null;
  onAddCommand: () => void;
  onEditCommand: (index: number) => void;
  onDeleteCommand: (index: number) => void | Promise<void>;
  onToggleCommand: (index: number, enabled: boolean) => void;
}

export const CommandsSettingsTab: React.FC<CommandsSettingsTabProps> = ({
  commands,
  onAddCommand,
  onEditCommand,
  onDeleteCommand,
  onToggleCommand,
}) => {
  const isMaxLimitReached = commands ? commands.length >= 10 : false;

  return (
    <ListManagementTab<CustomCommand>
      title="Slash Commands"
      description="Upload custom slash commands as markdown files. Commands will be available via /command-name syntax. Maximum 10 commands per user."
      items={commands}
      emptyIcon={Terminal}
      emptyText="No slash commands uploaded yet"
      emptyButtonText="Upload Your First Command"
      addButtonText="Upload Command"
      deleteConfirmTitle="Delete Command"
      deleteConfirmMessage={(command) =>
        `Are you sure you want to delete "${command.name}"? This action cannot be undone.`
      }
      getItemKey={(command) => command.name}
      onAdd={onAddCommand}
      onEdit={onEditCommand}
      onDelete={onDeleteCommand}
      maxLimit={10}
      isMaxLimitReached={isMaxLimitReached}
      footerContent={
        isMaxLimitReached && (
          <p className="mt-2 text-xs text-warning-600 dark:text-warning-400">
            Maximum command limit reached (10/10)
          </p>
        )
      }
      renderItem={(command, index) => (
        <>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <Terminal className="h-4 w-4 flex-shrink-0 text-brand-600 dark:text-brand-400" />
            <h3 className="min-w-0 max-w-full truncate font-mono text-sm font-medium text-text-primary dark:text-text-dark-primary sm:max-w-[250px]">
              /{command.name}
              {command.argument_hint && (
                <span className="ml-1 font-normal text-text-tertiary dark:text-text-dark-tertiary">
                  {command.argument_hint}
                </span>
              )}
            </h3>
            <Switch
              checked={command.enabled !== false}
              onCheckedChange={(checked) => onToggleCommand(index, checked)}
              size="sm"
              aria-label={`Toggle ${command.name} command`}
            />
          </div>
          <p className="mb-2 text-xs text-text-tertiary dark:text-text-dark-tertiary">
            {command.description}
          </p>
          {(command.allowed_tools || command.model) && (
            <div className="flex items-center gap-3 text-xs text-text-quaternary dark:text-text-dark-quaternary">
              {command.allowed_tools && (
                <span>
                  Tools: {command.allowed_tools.length === 0 ? 'All' : command.allowed_tools.length}
                </span>
              )}
              {command.model && <span className="capitalize">Model: {command.model}</span>}
            </div>
          )}
        </>
      )}
      logContext="CommandsSettingsTab"
    />
  );
};
