import { useCallback } from 'react';
import toast from 'react-hot-toast';
import { logger } from '@/utils/logger';
import { parseEventLog } from '@/utils/stream';
import { createAttachmentsFromFiles } from '@/utils/message';
import { extractPromptMention } from '@/utils/mentionParser';
import { MAX_MESSAGE_SIZE_BYTES } from '@/config/constants';
import type { ChatRequest, Message, AssistantStreamEvent, LineReview, StreamState } from '@/types';

interface UseMessageActionsParams {
  chatId: string | undefined;
  selectedModelId: string | null | undefined;
  permissionMode: 'plan' | 'ask' | 'auto';
  thinkingMode: string | null | undefined;
  setStreamState: (state: StreamState) => void;
  setCurrentMessageId: (id: string | null) => void;
  setError: (error: Error | null) => void;
  setWasAborted: (aborted: boolean) => void;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  addMessageToCache: (message: Message, userMessage?: Message) => void;
  startStream: (request: ChatRequest) => Promise<string>;
  storeBlobUrl: (file: File, url: string) => void;
  getReviewsForChat: (chatId: string) => LineReview[];
  clearReviewsForChat: (chatId: string) => void;
  setPendingUserMessageId: (id: string | null) => void;
  isLoading: boolean;
  isStreaming: boolean;
}

const isEmptyBotPlaceholder = (msg?: Message) =>
  !!msg?.is_bot && parseEventLog(msg?.content).length === 0;

export function useMessageActions({
  chatId,
  selectedModelId,
  permissionMode,
  thinkingMode,
  setStreamState,
  setCurrentMessageId,
  setError,
  setWasAborted,
  setMessages,
  addMessageToCache,
  startStream,
  storeBlobUrl,
  getReviewsForChat,
  clearReviewsForChat,
  setPendingUserMessageId,
  isLoading,
  isStreaming,
}: UseMessageActionsParams) {
  const sendMessage = useCallback(
    async (
      prompt: string,
      chatIdOverride?: string,
      userMessage?: Message,
      filesToSend?: File[],
    ) => {
      const normalizedPrompt = prompt.trim();
      if (!normalizedPrompt) return;

      if (!selectedModelId?.trim()) {
        setError(new Error('Please select an AI model'));
        setStreamState('error');
        return;
      }

      setStreamState('loading');
      setCurrentMessageId(null);
      setError(null);
      setWasAborted(false);

      try {
        const { promptName, cleanedMessage } = extractPromptMention(normalizedPrompt);

        const request: ChatRequest = {
          prompt: cleanedMessage || normalizedPrompt,
          model_id: selectedModelId,
          ...(chatIdOverride && { chat_id: chatIdOverride }),
          attached_files: filesToSend && filesToSend.length > 0 ? filesToSend : undefined,
          permission_mode: permissionMode,
          thinking_mode: thinkingMode || undefined,
          ...(promptName && { selected_prompt_name: promptName }),
        };

        const messageId = await startStream(request);

        setCurrentMessageId(messageId);
        setStreamState('streaming');

        const initialMessage: Message = {
          id: messageId,
          content: JSON.stringify([]),
          role: 'assistant',
          is_bot: true,
          attachments: [],
          created_at: new Date().toISOString(),
          model_id: selectedModelId ?? undefined,
        };

        setMessages((prev) => {
          const lastMessage = prev[prev.length - 1];
          if (isEmptyBotPlaceholder(lastMessage)) {
            return [...prev.slice(0, -1), initialMessage];
          }
          return [...prev, initialMessage];
        });
        addMessageToCache(initialMessage, userMessage);
      } catch (streamStartError) {
        setStreamState('error');
        const error =
          streamStartError instanceof Error
            ? streamStartError
            : new Error('Failed to start stream');
        setError(error);
        throw error;
      }
    },
    [
      addMessageToCache,
      permissionMode,
      selectedModelId,
      startStream,
      thinkingMode,
      setStreamState,
      setCurrentMessageId,
      setError,
      setWasAborted,
      setMessages,
    ],
  );

  const handleMessageSend = useCallback(
    async (inputMessage: string, inputFiles: File[]) => {
      const reviews = chatId ? getReviewsForChat(chatId) : [];
      const hasContent = inputMessage.trim() || reviews.length > 0;

      if (!hasContent || isLoading || isStreaming) return;

      if (!selectedModelId?.trim()) {
        setError(new Error('Please select an AI model'));
        return;
      }

      const messageEvents: AssistantStreamEvent[] = [];
      if (reviews.length > 0) {
        messageEvents.push({ type: 'code_review', reviews });
      }
      if (inputMessage.trim()) {
        messageEvents.push({ type: 'user_text', text: inputMessage });
      }

      const serialized = JSON.stringify(messageEvents);

      const encoder = new TextEncoder();
      const byteSize = encoder.encode(serialized).length;

      if (byteSize > MAX_MESSAGE_SIZE_BYTES) {
        toast.error(
          `Message too large (${Math.round(byteSize / 1024)}KB). Please reduce the number of review comments.`,
        );
        return;
      }

      const newMessage: Message = {
        id: crypto.randomUUID(),
        content: serialized,
        role: 'user',
        is_bot: false,
        model_id: selectedModelId,
        created_at: new Date().toISOString(),
        attachments: createAttachmentsFromFiles(inputFiles, storeBlobUrl),
      };

      setMessages((prev) => [...prev, newMessage]);
      setPendingUserMessageId(newMessage.id);

      try {
        await sendMessage(newMessage.content, chatId, newMessage, inputFiles);

        if (chatId && reviews.length > 0) {
          clearReviewsForChat(chatId);
        }

        setPendingUserMessageId(null);
        return { success: true };
      } catch (error) {
        logger.error('Failed to send message', 'useMessageActions', error);
        setMessages((prev) => prev.filter((msg) => msg.id !== newMessage.id));
        setPendingUserMessageId(null);
        return { success: false };
      }
    },
    [
      chatId,
      isLoading,
      isStreaming,
      selectedModelId,
      sendMessage,
      storeBlobUrl,
      getReviewsForChat,
      clearReviewsForChat,
      setPendingUserMessageId,
      setError,
      setMessages,
    ],
  );

  return {
    sendMessage,
    handleMessageSend,
  };
}
