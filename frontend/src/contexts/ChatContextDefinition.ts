import { createContext } from 'react';
import type { FileStructure, CustomAgent, CustomCommand, CustomPrompt } from '@/types';

export interface ChatContextValue {
  chatId?: string;
  sandboxId?: string;
  fileStructure: FileStructure[];
  customAgents: CustomAgent[];
  customSlashCommands: CustomCommand[];
  customPrompts: CustomPrompt[];
}

export const ChatContext = createContext<ChatContextValue | null>(null);
