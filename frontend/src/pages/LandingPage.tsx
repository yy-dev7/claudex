import { useState, useMemo, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Sidebar, useLayoutSidebar } from '@/components/layout';
import { Input } from '@/components/chat/message-input/Input';
import { Button } from '@/components/ui';
import { useChatStore, useAuthStore } from '@/store';
import {
  useInfiniteChatsQuery,
  useCreateChatMutation,
  useSettingsQuery,
  useModelSelection,
} from '@/hooks/queries';
import { mergeAgents } from '@/utils/settings';
import { ChatProvider } from '@/contexts/ChatContext';

const useExamplePrompts = () =>
  useMemo(
    () => [
      'Go to Amazon and find the best laptops under $1000',
      'Analyze this Excel file and create visualizations',
      'Deep research on quantum computing trends',
      'Build a full-stack app with FastAPI and React',
    ],
    [],
  );

export function LandingPage() {
  const navigate = useNavigate();
  const attachedFiles = useChatStore((state) => state.attachedFiles);
  const setAttachedFiles = useChatStore((state) => state.setAttachedFiles);
  const setCurrentChat = useChatStore((state) => state.setCurrentChat);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const { selectedModelId, selectModel } = useModelSelection({ enabled: isAuthenticated });

  const {
    data: chatsData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteChatsQuery({
    enabled: isAuthenticated,
  });

  const chats = useMemo(() => {
    if (!isAuthenticated || !chatsData?.pages?.length) return [];
    return chatsData.pages.flatMap((page) => page.items);
  }, [chatsData?.pages, isAuthenticated]);

  const createChat = useCreateChatMutation();
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const examplePrompts = useExamplePrompts();

  const { data: settings } = useSettingsQuery({
    enabled: isAuthenticated,
  });

  const allAgents = useMemo(() => {
    return mergeAgents(settings?.custom_agents);
  }, [settings?.custom_agents]);

  const enabledSlashCommands = useMemo(() => {
    return settings?.custom_slash_commands?.filter((cmd) => cmd.enabled) || [];
  }, [settings?.custom_slash_commands]);

  const customPrompts = useMemo(() => {
    return settings?.custom_prompts || [];
  }, [settings?.custom_prompts]);

  useEffect(() => {
    setCurrentChat(null);
  }, [setCurrentChat]);

  const handleFileAttach = useCallback(
    (files: File[]) => {
      setAttachedFiles(files);
    },
    [setAttachedFiles],
  );

  const handleNewChat = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmedPrompt = message.trim();
      if (!trimmedPrompt || isLoading) return;

      if (!isAuthenticated) {
        navigate('/signup');
        return;
      }

      if (!selectedModelId?.trim()) {
        toast.error('Please select an AI model');
        return;
      }

      setIsLoading(true);
      try {
        const title = trimmedPrompt.replace(/\s+/g, ' ').slice(0, 80) || 'New Chat';
        const newChat = await createChat.mutateAsync({ title, model_id: selectedModelId });
        setMessage('');
        navigate(`/chat/${newChat.id}`, { state: { initialPrompt: trimmedPrompt } });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to create chat');
      } finally {
        setIsLoading(false);
      }
    },
    [createChat, isAuthenticated, isLoading, message, navigate, selectedModelId],
  );

  const handleChatSelect = useCallback(
    (chatId: string) => {
      navigate(`/chat/${chatId}`);
    },
    [navigate],
  );

  const handleExampleClick = useCallback((prompt: string) => {
    setMessage(prompt);
  }, []);

  const sidebarContent = useMemo(() => {
    if (!isAuthenticated) return null;

    return (
      <Sidebar
        chats={chats}
        selectedChatId={null}
        onChatSelect={handleChatSelect}
        hasNextPage={hasNextPage}
        fetchNextPage={fetchNextPage}
        isFetchingNextPage={isFetchingNextPage}
      />
    );
  }, [chats, fetchNextPage, handleChatSelect, hasNextPage, isAuthenticated, isFetchingNextPage]);

  useLayoutSidebar(sidebarContent);

  return (
    <div className="flex h-full flex-col">
      <div className="relative flex flex-1">
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-surface-secondary/50 via-transparent to-brand-50/30 dark:from-surface-dark/50 dark:via-transparent dark:to-brand-900/10" />
        <div className="flex flex-1 items-center justify-center px-4 pb-10">
          <div className="w-full max-w-3xl">
            <div className="mb-8 space-y-6 text-center">
              <div>
                <h1 className="mb-2 text-3xl font-medium text-text-primary dark:text-text-dark-primary">
                  What would you like to work on?
                </h1>
                <p className="text-sm text-text-tertiary dark:text-text-dark-tertiary">
                  Build anything. No limitations.
                </p>
              </div>
            </div>
            <ChatProvider
              customAgents={allAgents}
              customSlashCommands={enabledSlashCommands}
              customPrompts={customPrompts}
            >
              <Input
                message={message}
                setMessage={setMessage}
                onSubmit={handleNewChat}
                onAttach={handleFileAttach}
                attachedFiles={attachedFiles}
                isLoading={isLoading}
                selectedModelId={selectedModelId}
                onModelChange={selectModel}
              />
            </ChatProvider>
            <div className="mt-4">
              <div className="mx-auto flex max-w-4xl flex-wrap justify-center gap-3">
                {examplePrompts.map((prompt) => (
                  <Button
                    key={prompt}
                    onClick={() => handleExampleClick(prompt)}
                    variant="unstyled"
                    className="whitespace-nowrap rounded-full border border-border bg-surface-secondary px-4 py-2.5 text-xs text-text-secondary transition-all duration-200 hover:border-brand-500/30 hover:bg-surface-tertiary dark:border-border-dark dark:bg-surface-dark-secondary dark:text-text-dark-secondary dark:hover:border-brand-400/30 dark:hover:bg-surface-dark-tertiary"
                  >
                    {prompt}
                  </Button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
