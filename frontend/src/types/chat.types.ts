import type { ToolEventPayload } from './tools.types';
import type { LineReview } from './review.types';

export interface MessageAttachment {
  id: string;
  message_id: string;
  file_url: string;
  file_type: 'image' | 'pdf' | 'xlsx';
  filename?: string;
  created_at: string;
}

export interface Message {
  id: string;
  chat_id: string;
  content: string;
  is_bot?: boolean;
  role: 'user' | 'assistant';
  model_id?: string;
  attachments?: MessageAttachment[];
  created_at: string;
}

export type AssistantStreamEvent =
  | { type: 'assistant_text'; text: string }
  | { type: 'assistant_thinking'; thinking: string }
  | { type: 'tool_started'; tool: ToolEventPayload }
  | { type: 'tool_completed'; tool: ToolEventPayload }
  | { type: 'tool_failed'; tool: ToolEventPayload }
  | { type: 'user_text'; text: string }
  | { type: 'code_review'; reviews: LineReview[] }
  | {
      type: 'system';
      data?: { context_usage?: { tokens_used: number; context_window: number } } & Record<
        string,
        unknown
      >;
    }
  | {
      type: 'permission_request';
      request_id: string;
      tool_name: string;
      tool_input: Record<string, unknown>;
    };

export interface Chat {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  sandbox_id?: string;
  context_token_usage?: number;
  pinned_at?: string | null;
}

export interface ChatRequest {
  prompt: string;
  chat_id?: string;
  model_id: string;
  attached_files?: File[];
  permission_mode: 'plan' | 'ask' | 'auto';
  thinking_mode?: string;
  selected_prompt_name?: string;
}

export interface CreateChatRequest {
  title: string;
  model_id: string;
}

export interface PreviewLinksResponse {
  links: Array<{
    port: number;
    preview_url: string;
  }>;
}

export type ModelProvider = 'anthropic' | 'zai' | 'openrouter';

export interface Model {
  id: string;
  model_id: string;
  name: string;
  provider: ModelProvider;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ContextUsage {
  tokens_used: number;
  context_window: number;
  percentage: number;
}

export interface PermissionRequest {
  request_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
}

export interface QuestionOption {
  label: string;
  description?: string;
}

export interface UserQuestion {
  question: string;
  header?: string;
  options?: QuestionOption[];
  multiSelect?: boolean;
}

export interface AskUserQuestionInput {
  questions: UserQuestion[];
}
