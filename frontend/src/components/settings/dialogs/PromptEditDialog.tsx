import type { CustomPrompt } from '@/types';
import { Button, Input, Label, Textarea } from '@/components/ui';
import { BaseModal } from '@/components/ui/shared/BaseModal';

interface PromptEditDialogProps {
  isOpen: boolean;
  isEditing: boolean;
  prompt: CustomPrompt;
  error: string | null;
  onClose: () => void;
  onSubmit: () => void;
  onPromptChange: <K extends keyof CustomPrompt>(field: K, value: CustomPrompt[K]) => void;
}

export const PromptEditDialog: React.FC<PromptEditDialogProps> = ({
  isOpen,
  isEditing,
  prompt,
  error,
  onClose,
  onSubmit,
  onPromptChange,
}) => {
  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      size="4xl"
      className="max-h-[90vh] overflow-y-auto shadow-strong"
    >
      <div className="p-6">
        <h3 className="mb-4 text-lg font-semibold text-text-primary dark:text-text-dark-primary">
          {isEditing ? 'Edit Prompt' : 'Add Prompt'}
        </h3>

        {error && (
          <div className="mb-4 rounded-md border border-error-200 bg-error-50 p-3 dark:border-error-800 dark:bg-error-900/20">
            <p className="text-xs text-error-700 dark:text-error-400">{error}</p>
          </div>
        )}

        <div className="space-y-4">
          <div>
            <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
              Name
            </Label>
            <Input
              value={prompt.name}
              onChange={(e) => onPromptChange('name', e.target.value)}
              placeholder="code-reviewer"
              className="text-sm"
            />
            <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              A unique identifier for this prompt (use @prompt:name to select)
            </p>
          </div>

          <div>
            <Label className="mb-1.5 text-sm text-text-primary dark:text-text-dark-primary">
              Content
            </Label>
            <Textarea
              value={prompt.content}
              onChange={(e) => onPromptChange('content', e.target.value)}
              placeholder="You are an expert code reviewer..."
              className="min-h-[300px] font-mono text-sm"
              rows={15}
            />
            <p className="mt-1 text-xs text-text-tertiary dark:text-text-dark-tertiary">
              The system prompt content. Runtime context and integrations will be automatically
              appended.
            </p>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <Button type="button" onClick={onClose} variant="outline" size="sm">
            Cancel
          </Button>
          <Button
            type="button"
            onClick={onSubmit}
            variant="primary"
            size="sm"
            disabled={!prompt.name.trim() || !prompt.content.trim()}
          >
            {isEditing ? 'Update Prompt' : 'Add Prompt'}
          </Button>
        </div>
      </div>
    </BaseModal>
  );
};
