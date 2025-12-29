import { Button, Select, Switch } from '@/components/ui';
import type { UserSettings, GeneralSecretFieldConfig, ApiFieldKey, SandboxProvider } from '@/types';
import { SecretInput } from '@/components/settings/inputs/SecretInput';
import { CodexAuthUpload } from '@/components/settings/inputs/CodexAuthUpload';

interface GeneralSettingsTabProps {
  fields: GeneralSecretFieldConfig[];
  settings: UserSettings;
  revealedFields: Record<ApiFieldKey, boolean>;
  onSecretChange: (field: ApiFieldKey, value: string) => void;
  onToggleVisibility: (field: ApiFieldKey) => void;
  onDeleteAllChats: () => void;
  onNotificationSoundChange: (enabled: boolean) => void;
  onSandboxProviderChange: (provider: SandboxProvider | null) => void;
  onAutoCompactDisabledChange: (disabled: boolean) => void;
  onCodexAuthChange: (content: string | null) => void;
}

export const GeneralSettingsTab: React.FC<GeneralSettingsTabProps> = ({
  fields,
  settings,
  revealedFields,
  onSecretChange,
  onToggleVisibility,
  onDeleteAllChats,
  onNotificationSoundChange,
  onSandboxProviderChange,
  onAutoCompactDisabledChange,
  onCodexAuthChange,
}) => (
  <div className="space-y-6">
    <div>
      <h2 className="mb-4 text-sm font-medium text-text-primary dark:text-text-dark-primary">
        Sandbox Environment
      </h2>
      <div className="space-y-4">
        <div>
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
                Sandbox Provider
              </h3>
              <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                Choose between cloud (E2B) or local (Docker) sandbox execution.
              </p>
            </div>
          </div>
          <div className="mt-2 max-w-xs">
            <Select
              value={settings.sandbox_provider ?? 'e2b'}
              onChange={(e) =>
                onSandboxProviderChange(
                  e.target.value === 'e2b' || e.target.value === 'docker' ? e.target.value : null,
                )
              }
            >
              <option value="e2b">E2B (Cloud)</option>
              <option value="docker">Docker (Local)</option>
            </Select>
            <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              {settings.sandbox_provider === 'docker'
                ? 'Local Docker requires Docker daemon running on your server.'
                : 'E2B requires an API key configured below.'}
            </p>
          </div>
        </div>
        {fields.map((field) => (
          <div key={field.key}>
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
                  {field.label}
                </h3>
                <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                  {field.description}
                </p>
              </div>
            </div>
            <SecretInput
              value={settings[field.key] ?? ''}
              placeholder={field.placeholder}
              isVisible={revealedFields[field.key]}
              onChange={(value) => onSecretChange(field.key, value)}
              onToggleVisibility={() => onToggleVisibility(field.key)}
              helperText={field.helperText}
            />
          </div>
        ))}
      </div>
    </div>

    <div>
      <h2 className="mb-4 text-sm font-medium text-text-primary dark:text-text-dark-primary">
        Notifications
      </h2>
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-4 sm:items-center">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
              Sound Notification
            </h3>
            <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              Play a sound when the assistant finishes responding.
            </p>
          </div>
          <Switch
            checked={settings.notification_sound_enabled ?? true}
            onCheckedChange={onNotificationSoundChange}
          />
        </div>
      </div>
    </div>

    <div>
      <h2 className="mb-4 text-sm font-medium text-text-primary dark:text-text-dark-primary">
        Claude Settings
      </h2>
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
              Disable Auto Compact
            </h3>
            <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              Prevents Claude from automatically compacting conversation history.
            </p>
          </div>
          <Switch
            checked={settings.auto_compact_disabled ?? false}
            onCheckedChange={onAutoCompactDisabledChange}
          />
        </div>
      </div>
    </div>

    <div>
      <h2 className="mb-4 text-sm font-medium text-text-primary dark:text-text-dark-primary">
        OpenAI Codex
      </h2>
      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
            Codex Authentication
          </h3>
          <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
            Upload your auth.json file from ~/.codex/ for OpenAI Codex CLI authentication.
          </p>
          <CodexAuthUpload value={settings.codex_auth_json} onChange={onCodexAuthChange} />
        </div>
      </div>
    </div>

    <div>
      <h2 className="mb-4 text-sm font-medium text-text-primary dark:text-text-dark-primary">
        Data Management
      </h2>
      <div className="space-y-4">
        <div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <div className="min-w-0 flex-1">
              <h3 className="text-sm font-medium text-text-primary dark:text-text-dark-primary">
                Delete All Chats
              </h3>
              <p className="mt-0.5 text-xs text-text-tertiary dark:text-text-dark-tertiary">
                Permanently delete all chat history. This action cannot be undone.
              </p>
            </div>
            <Button
              type="button"
              onClick={onDeleteAllChats}
              variant="outline"
              size="sm"
              className="w-full border-error-200 text-error-600 hover:bg-error-50 dark:border-error-800 dark:text-error-400 dark:hover:bg-error-400/10 sm:w-auto"
            >
              Delete All
            </Button>
          </div>
        </div>
      </div>
    </div>
  </div>
);
