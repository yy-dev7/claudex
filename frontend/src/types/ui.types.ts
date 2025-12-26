import type { Chat } from './chat.types';
import type { ToolAggregate } from './tools.types';

export type ToolComponent = React.FC<{ tool: ToolAggregate; chatId?: string }>;

export type Theme = 'light' | 'dark';

type MentionType = 'file' | 'agent' | 'prompt';

export interface MentionItem {
  type: MentionType;
  name: string;
  path: string;
  description?: string;
}

export interface ThemeState {
  theme: Theme;
  toggleTheme: () => void;
}

export interface ModelSelectionState {
  selectedModelId: string;
  selectModel: (modelId: string) => void;
}

export interface PermissionModeState {
  permissionMode: 'plan' | 'ask' | 'auto';
  setPermissionMode: (mode: 'plan' | 'ask' | 'auto') => void;
}

export interface ThinkingModeState {
  thinkingMode: string | null;
  setThinkingMode: (mode: string | null) => void;
}

export type ViewType =
  | 'agent'
  | 'editor'
  | 'ide'
  | 'terminal'
  | 'secrets'
  | 'webPreview'
  | 'mobilePreview';

export interface UIState {
  currentChat: Chat | null;
  attachedFiles: File[];
  sidebarOpen: boolean;
  currentView: ViewType;
}

export interface UIActions {
  setAttachedFiles: (files: File[]) => void;
  setCurrentChat: (chat: Chat | null) => void;
  setSidebarOpen: (isOpen: boolean) => void;
  setCurrentView: (view: ViewType) => void;
}

export interface SlashCommand {
  value: string;
  label: string;
  description?: string;
}
