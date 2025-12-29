import { useEffect, useMemo, useCallback } from 'react';
import { useParams, Navigate, useNavigate } from 'react-router-dom';
import { useShallow } from 'zustand/react/shallow';
import { Sidebar, useLayoutSidebar } from '@/components/layout';
import { useUIStore, useChatStore } from '@/store';
import { ViewSwitcher } from '@/components/ui/ViewSwitcher';
import {
  TerminalView,
  SecretsView,
  WebPreviewView,
  MobilePreviewView,
  IDEView,
} from '@/components/views';
import { Chat as ChatComponent } from '@/components/chat/chat-window/Chat';
import { Editor } from '@/components/editor/editor-core/Editor';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStreaming } from '@/hooks/useChatStreaming';
import { usePermissionRequest } from '@/hooks/usePermissionRequest';
import { useUserQuestion } from '@/hooks/useUserQuestion';
import { ToolPermissionModal } from '@/components/chat/tools/ToolPermissionModal';
import { AskUserQuestionModal } from '@/components/chat/tools/AskUserQuestionModal';
import { useInitialPrompt } from '@/hooks/useInitialPrompt';
import { useEditorState } from '@/hooks/useEditorState';
import { useMessageInitialization } from '@/hooks/useMessageInitialization';
import { useChatData } from '@/hooks/useChatData';
import { useSandboxFiles } from '@/hooks/useSandboxFiles';
import { useContextUsageState } from '@/hooks/useContextUsageState';
import { useSettingsQuery, useModelSelection } from '@/hooks/queries';
import { mergeAgents } from '@/utils/settings';

export function ChatPage() {
  const { chatId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { attachedFiles, setAttachedFiles, setCurrentChat } = useChatStore(
    useShallow((state) => ({
      attachedFiles: state.attachedFiles,
      setAttachedFiles: state.setAttachedFiles,
      setCurrentChat: state.setCurrentChat,
    })),
  );

  const { selectedModelId, selectModel } = useModelSelection();

  const { permissionMode, thinkingMode, currentView, setCurrentView } = useUIStore(
    useShallow((state) => ({
      permissionMode: state.permissionMode,
      thinkingMode: state.thinkingMode,
      currentView: state.currentView,
      setCurrentView: state.setCurrentView,
    })),
  );

  const {
    initialPrompt,
    setInitialPrompt,
    initialPromptSent,
    setInitialPromptSent,
    initialPromptFromRoute,
  } = useInitialPrompt();

  const { chats, currentChat, fetchedMessages, hasFetchedMessages, chatsQueryMeta, messagesQuery } =
    useChatData(chatId);

  const { fileStructure, isFileMetadataLoading, refetchFilesMetadata } = useSandboxFiles(
    currentChat,
    chatId,
  );

  const { contextUsage, refetchContextUsage } = useContextUsageState(chatId, currentChat);

  const { data: settings } = useSettingsQuery();

  const allAgents = useMemo(() => mergeAgents(settings?.custom_agents), [settings?.custom_agents]);

  const enabledSlashCommands = useMemo(() => {
    return settings?.custom_slash_commands?.filter((cmd) => cmd.enabled) || [];
  }, [settings?.custom_slash_commands]);

  const customPrompts = useMemo(() => {
    return settings?.custom_prompts || [];
  }, [settings?.custom_prompts]);

  const { selectedFile, setSelectedFile, isRefreshing, handleRefresh, handleFileSelect } =
    useEditorState(refetchFilesMetadata);

  const {
    pendingRequest,
    isLoading: isPermissionLoading,
    handlePermissionRequest,
    handleApprove,
    handleReject,
  } = usePermissionRequest(chatId);

  const {
    pendingRequest: userQuestionRequest,
    isLoading: isQuestionLoading,
    error: questionError,
    handleSubmitAnswers,
    handleCancel: handleQuestionCancel,
  } = useUserQuestion(chatId);

  const streamingState = useChatStreaming({
    chatId,
    currentChat,
    fetchedMessages,
    hasFetchedMessages,
    isInitialLoading: messagesQuery.isLoading,
    queryClient,
    refetchFilesMetadata,
    refetchContextUsage,
    selectedModelId,
    permissionMode,
    thinkingMode,
    onPermissionRequest: handlePermissionRequest,
  });

  const {
    messages,
    sendMessage,
    isLoading,
    isStreaming,
    error,
    wasAborted,
    setWasAborted,
    setMessages,
  } = streamingState;

  useMessageInitialization({
    fetchedMessages,
    chatId,
    selectedModelId,
    hasMessages: messages.length > 0,
    initialPromptFromRoute,
    initialPromptSent,
    wasAborted,
    attachedFiles,
    isLoading,
    isStreaming,
    setMessages,
    setInitialPrompt,
  });

  useEffect(() => {
    if (
      initialPrompt &&
      messages.length === 1 &&
      !isLoading &&
      !isStreaming &&
      !initialPromptSent &&
      !error &&
      !messagesQuery.isLoading &&
      !hasFetchedMessages
    ) {
      const userMessage = messages[0];
      sendMessage(initialPrompt, chatId, userMessage, attachedFiles);
      setInitialPromptSent(true);
      setAttachedFiles([]);
    }
  }, [
    initialPrompt,
    messages,
    messages.length,
    isLoading,
    isStreaming,
    sendMessage,
    chatId,
    initialPromptSent,
    error,
    setAttachedFiles,
    messagesQuery.isLoading,
    hasFetchedMessages,
    attachedFiles,
    setInitialPromptSent,
  ]);

  useEffect(() => {
    setCurrentChat(currentChat || null);
  }, [currentChat, setCurrentChat]);

  useEffect(() => {
    setInitialPromptSent(false);
    setSelectedFile(null);
    setCurrentView('agent');
  }, [chatId, setInitialPromptSent, setSelectedFile, setCurrentView]);

  const handleChatSelect = useCallback(
    (selectedChatId: string) => {
      navigate(`/chat/${selectedChatId}`);
    },
    [navigate],
  );

  const handleRestoreSuccess = useCallback(() => {
    setWasAborted(false);
    messagesQuery.refetch();
    if (currentChat?.sandbox_id) {
      refetchFilesMetadata();
    }
  }, [setWasAborted, messagesQuery, currentChat?.sandbox_id, refetchFilesMetadata]);

  const sidebarContent = useMemo(() => {
    if (currentView !== 'agent') return null;
    return (
      <Sidebar
        chats={chats}
        selectedChatId={chatId || null}
        onChatSelect={handleChatSelect}
        hasNextPage={chatsQueryMeta.hasNextPage}
        fetchNextPage={chatsQueryMeta.fetchNextPage}
        isFetchingNextPage={chatsQueryMeta.isFetchingNextPage}
        hasActivityBar={true}
      />
    );
  }, [
    currentView,
    chats,
    chatId,
    chatsQueryMeta.fetchNextPage,
    handleChatSelect,
    chatsQueryMeta.hasNextPage,
    chatsQueryMeta.isFetchingNextPage,
  ]);

  useLayoutSidebar(sidebarContent);

  const isTerminalView = currentView === 'terminal';

  if (!chatId) return <Navigate to="/" />;

  return (
    <div className="relative flex h-full">
      <ViewSwitcher />
      <div className="ml-12 flex h-full flex-1 overflow-hidden bg-surface text-text-primary dark:bg-surface-dark dark:text-text-dark-primary">
        <div className={`${isTerminalView ? 'flex' : 'hidden'} h-full flex-1`}>
          <TerminalView currentChat={currentChat} isVisible={isTerminalView} />
        </div>
        {currentView === 'agent' && (
          <ChatComponent
            messages={messages}
            copiedMessageId={streamingState.copiedMessageId}
            isLoading={isLoading}
            isStreaming={isStreaming}
            isInitialLoading={messagesQuery.isLoading}
            error={error}
            onCopy={streamingState.handleCopy}
            inputMessage={streamingState.inputMessage}
            setInputMessage={streamingState.setInputMessage}
            onMessageSend={streamingState.handleMessageSend}
            onStopStream={streamingState.handleStop}
            onAttach={streamingState.setInputFiles}
            selectedModelId={selectedModelId}
            onModelChange={selectModel}
            attachedFiles={streamingState.inputFiles}
            contextUsage={contextUsage}
            sandboxId={currentChat?.sandbox_id}
            chatId={chatId}
            onDismissError={streamingState.handleDismissError}
            fetchNextPage={messagesQuery.fetchNextPage}
            hasNextPage={messagesQuery.hasNextPage}
            isFetchingNextPage={messagesQuery.isFetchingNextPage}
            onRestoreSuccess={handleRestoreSuccess}
            fileStructure={fileStructure}
            customAgents={allAgents}
            customSlashCommands={enabledSlashCommands}
            customPrompts={customPrompts}
          />
        )}
        {currentView === 'editor' && (
          <Editor
            files={fileStructure}
            isExpanded={true}
            selectedFile={selectedFile}
            onFileSelect={handleFileSelect}
            chatId={chatId}
            currentChat={currentChat}
            isSandboxSyncing={isFileMetadataLoading}
            onRefresh={handleRefresh}
            isRefreshing={isRefreshing}
          />
        )}
        {currentView === 'ide' && (
          <IDEView sandboxId={currentChat?.sandbox_id} isActive={currentView === 'ide'} />
        )}
        {currentView === 'secrets' && (
          <SecretsView chatId={chatId} sandboxId={currentChat?.sandbox_id} />
        )}
        {currentView === 'webPreview' && (
          <WebPreviewView sandboxId={currentChat?.sandbox_id} isActive={true} />
        )}
        {currentView === 'mobilePreview' && (
          <MobilePreviewView sandboxId={currentChat?.sandbox_id} />
        )}
      </div>

      <ToolPermissionModal
        request={pendingRequest}
        onApprove={handleApprove}
        onReject={handleReject}
        isLoading={isPermissionLoading}
      />

      <AskUserQuestionModal
        request={userQuestionRequest}
        onSubmit={handleSubmitAnswers}
        onCancel={handleQuestionCancel}
        isLoading={isQuestionLoading}
        error={questionError}
      />
    </div>
  );
}
