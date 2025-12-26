import { memo } from 'react';
import { SlashCommandsPanel } from './SlashCommandsPanel';
import { MentionSuggestionsPanel } from './MentionSuggestionsPanel';
import type { MentionItem, SlashCommand } from '@/types';

interface InputSuggestionsPanelProps {
  isMentionActive: boolean;
  slashCommands: SlashCommand[];
  highlightedSlashIndex: number;
  onSlashSelect: (command: SlashCommand) => void;
  mentionFiles: MentionItem[];
  mentionAgents: MentionItem[];
  mentionPrompts: MentionItem[];
  highlightedMentionIndex: number;
  onMentionSelect: (item: MentionItem) => void;
}

export const InputSuggestionsPanel = memo(function InputSuggestionsPanel({
  isMentionActive,
  slashCommands,
  highlightedSlashIndex,
  onSlashSelect,
  mentionFiles,
  mentionAgents,
  mentionPrompts,
  highlightedMentionIndex,
  onMentionSelect,
}: InputSuggestionsPanelProps) {
  if (isMentionActive) {
    return (
      <MentionSuggestionsPanel
        files={mentionFiles}
        agents={mentionAgents}
        prompts={mentionPrompts}
        highlightedIndex={highlightedMentionIndex}
        onSelect={onMentionSelect}
      />
    );
  }

  return (
    <SlashCommandsPanel
      suggestions={slashCommands}
      highlightedIndex={highlightedSlashIndex}
      onSelect={onSlashSelect}
    />
  );
});
