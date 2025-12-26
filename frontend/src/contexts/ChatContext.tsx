import { type ReactNode } from 'react';
import type { FileStructure, CustomAgent, CustomCommand, CustomPrompt } from '@/types';
import { ChatContext } from './ChatContextDefinition';

interface ChatProviderProps {
  chatId?: string;
  sandboxId?: string;
  fileStructure?: FileStructure[];
  customAgents?: CustomAgent[];
  customSlashCommands?: CustomCommand[];
  customPrompts?: CustomPrompt[];
  children: ReactNode;
}

export function ChatProvider({
  chatId,
  sandboxId,
  fileStructure = [],
  customAgents = [],
  customSlashCommands = [],
  customPrompts = [],
  children,
}: ChatProviderProps) {
  return (
    <ChatContext.Provider
      value={{ chatId, sandboxId, fileStructure, customAgents, customSlashCommands, customPrompts }}
    >
      {children}
    </ChatContext.Provider>
  );
}
