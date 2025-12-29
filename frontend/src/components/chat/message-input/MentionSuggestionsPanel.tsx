import { memo, useEffect, useRef } from 'react';
import { Button } from '@/components/ui';
import type { MentionItem } from '@/types';

interface MentionSuggestionsPanelProps {
  files: MentionItem[];
  agents: MentionItem[];
  prompts: MentionItem[];
  highlightedIndex: number;
  onSelect: (item: MentionItem) => void;
}

export const MentionSuggestionsPanel = memo(function MentionSuggestionsPanel({
  files,
  agents,
  prompts,
  highlightedIndex,
  onSelect,
}: MentionSuggestionsPanelProps) {
  const mentionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const hasFiles = files.length > 0;
  const hasAgents = agents.length > 0;
  const hasPrompts = prompts.length > 0;
  const hasSuggestions = hasFiles || hasAgents || hasPrompts;

  useEffect(() => {
    if (highlightedIndex >= 0 && mentionRefs.current[highlightedIndex]) {
      mentionRefs.current[highlightedIndex]?.scrollIntoView({
        block: 'nearest',
        behavior: 'smooth',
      });
    }
  }, [highlightedIndex]);

  if (!hasSuggestions) return null;

  return (
    <div className="absolute bottom-full left-0 right-0 z-20 mb-2">
      <div className="max-h-64 overflow-y-auto rounded-lg border border-border bg-surface shadow-sm dark:border-border-dark dark:bg-surface-dark">
        <div className="py-1">
          {hasFiles && (
            <>
              <div className="px-3 py-1 text-2xs font-semibold uppercase tracking-wide text-text-tertiary dark:text-text-dark-tertiary">
                Files
              </div>
              {files.map((file, index) => {
                const isActive = index === highlightedIndex;
                return (
                  <Button
                    key={file.path}
                    ref={(el) => {
                      mentionRefs.current[index] = el;
                    }}
                    type="button"
                    variant="unstyled"
                    className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${
                      isActive
                        ? 'bg-surface-tertiary dark:bg-surface-dark-tertiary'
                        : 'hover:bg-surface-secondary dark:hover:bg-surface-dark-secondary'
                    }`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      onSelect(file);
                    }}
                  >
                    <span className="text-sm">📄</span>
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span
                        className={`font-mono text-xs leading-tight ${
                          isActive
                            ? 'text-text-primary dark:text-text-dark-primary'
                            : 'text-text-secondary dark:text-text-dark-secondary'
                        }`}
                      >
                        {file.name}
                      </span>
                      <span className="truncate text-2xs leading-tight text-text-tertiary dark:text-text-dark-tertiary">
                        {file.path}
                      </span>
                    </div>
                  </Button>
                );
              })}
            </>
          )}
          {hasAgents && (
            <>
              <div className="px-3 py-1 text-2xs font-semibold uppercase tracking-wide text-text-tertiary dark:text-text-dark-tertiary">
                Agents
              </div>
              {agents.map((agent, index) => {
                const globalIndex = files.length + index;
                const isActive = globalIndex === highlightedIndex;
                return (
                  <Button
                    key={agent.path}
                    ref={(el) => {
                      mentionRefs.current[globalIndex] = el;
                    }}
                    type="button"
                    variant="unstyled"
                    className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${
                      isActive
                        ? 'bg-surface-tertiary dark:bg-surface-dark-tertiary'
                        : 'hover:bg-surface-secondary dark:hover:bg-surface-dark-secondary'
                    }`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      onSelect(agent);
                    }}
                  >
                    <span className="text-sm">🤖</span>
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span
                        className={`text-xs font-medium leading-tight ${
                          isActive
                            ? 'text-text-primary dark:text-text-dark-primary'
                            : 'text-text-secondary dark:text-text-dark-secondary'
                        }`}
                      >
                        {agent.name}
                      </span>
                      {agent.description && (
                        <span className="truncate text-2xs leading-tight text-text-tertiary dark:text-text-dark-tertiary">
                          {agent.description}
                        </span>
                      )}
                    </div>
                  </Button>
                );
              })}
            </>
          )}
          {hasPrompts && (
            <>
              <div className="px-3 py-1 text-2xs font-semibold uppercase tracking-wide text-text-tertiary dark:text-text-dark-tertiary">
                Prompts
              </div>
              {prompts.map((prompt, index) => {
                const globalIndex = files.length + agents.length + index;
                const isActive = globalIndex === highlightedIndex;
                return (
                  <Button
                    key={prompt.path}
                    ref={(el) => {
                      mentionRefs.current[globalIndex] = el;
                    }}
                    type="button"
                    variant="unstyled"
                    className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${
                      isActive
                        ? 'bg-surface-tertiary dark:bg-surface-dark-tertiary'
                        : 'hover:bg-surface-secondary dark:hover:bg-surface-dark-secondary'
                    }`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      onSelect(prompt);
                    }}
                  >
                    <span className="text-sm">📝</span>
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span
                        className={`text-xs font-medium leading-tight ${
                          isActive
                            ? 'text-text-primary dark:text-text-dark-primary'
                            : 'text-text-secondary dark:text-text-dark-secondary'
                        }`}
                      >
                        {prompt.name}
                      </span>
                    </div>
                  </Button>
                );
              })}
            </>
          )}
        </div>
      </div>
    </div>
  );
});
