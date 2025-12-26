export interface User {
  id: string;
  email: string;
  username: string;
  is_verified: boolean;
  email_verification_required: boolean;
  daily_message_limit: number | null;
}

export interface UserUsage {
  messages_used_today: number;
  daily_message_limit: number | null;
  messages_remaining: number;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface CustomAgent {
  name: string;
  description: string;
  content: string;
  enabled: boolean;
  model?: 'sonnet' | 'opus' | 'haiku' | 'inherit' | null;
  allowed_tools?: string[] | null;
  [key: string]: unknown;
}

export interface CustomMcp {
  name: string;
  description: string;
  command_type: 'npx' | 'bunx' | 'uvx' | 'http';
  package?: string;
  url?: string;
  env_vars?: Record<string, string>;
  args?: string[];
  enabled: boolean;
  [key: string]: unknown;
}

export interface CustomEnvVar {
  key: string;
  value: string;
  [key: string]: unknown;
}

export interface CustomSkill {
  name: string;
  description: string;
  enabled: boolean;
  size_bytes: number;
  file_count: number;
}

export interface CustomCommand {
  name: string;
  description: string;
  content: string;
  enabled: boolean;
  argument_hint?: string | null;
  allowed_tools?: string[] | null;
  model?:
    | 'claude-sonnet-4-5-20250929'
    | 'claude-opus-4-5-20251101'
    | 'claude-haiku-4-5-20251001'
    | null;
}

export interface CustomPrompt {
  name: string;
  content: string;
}

export type SandboxProvider = 'e2b' | 'docker';

export interface UserSettings {
  id: string;
  user_id: string;
  github_personal_access_token: string | null;
  e2b_api_key: string | null;
  claude_code_oauth_token: string | null;
  z_ai_api_key: string | null;
  openrouter_api_key: string | null;
  custom_instructions: string | null;
  custom_agents: CustomAgent[] | null;
  custom_mcps: CustomMcp[] | null;
  custom_env_vars: CustomEnvVar[] | null;
  custom_skills: CustomSkill[] | null;
  custom_slash_commands: CustomCommand[] | null;
  custom_prompts: CustomPrompt[] | null;
  notification_sound_enabled?: boolean;
  sandbox_provider: SandboxProvider;
  created_at: string;
  updated_at: string;
}

export type UserSettingsUpdate = Partial<
  Omit<UserSettings, 'id' | 'user_id' | 'created_at' | 'updated_at'>
>;
