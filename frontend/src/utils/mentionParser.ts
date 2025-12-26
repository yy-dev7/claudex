interface MentionParseResult {
  isActive: boolean;
  query: string;
  mentionStartPos: number;
  mentionEndPos: number;
}

const INACTIVE_RESULT: MentionParseResult = {
  isActive: false,
  query: '',
  mentionStartPos: -1,
  mentionEndPos: -1,
} as const;

export interface ExtractedPromptMention {
  promptName: string | null;
  cleanedMessage: string;
}

export const extractPromptMention = (message: string): ExtractedPromptMention => {
  const promptMentionRegex = /@prompt:([^\s]+)/g;
  const match = promptMentionRegex.exec(message);

  if (!match) {
    return { promptName: null, cleanedMessage: message };
  }

  const promptName = match[1];
  const cleanedMessage = message.replace(match[0], '').trim();

  return { promptName, cleanedMessage };
};

export const parseMentionQuery = (message: string, cursorPosition: number): MentionParseResult => {
  const textBeforeCursor = message.slice(0, cursorPosition);
  const lastAtIndex = textBeforeCursor.lastIndexOf('@');

  if (lastAtIndex === -1) {
    return INACTIVE_RESULT;
  }

  const charBeforeAt = lastAtIndex > 0 ? message[lastAtIndex - 1] : ' ';
  const isValidStart = charBeforeAt === ' ' || charBeforeAt === '\n' || lastAtIndex === 0;

  if (!isValidStart) {
    return INACTIVE_RESULT;
  }

  const textAfterAt = message.slice(lastAtIndex + 1, cursorPosition);

  if (textAfterAt.includes(' ') || textAfterAt.includes('\n')) {
    return INACTIVE_RESULT;
  }

  return {
    isActive: true,
    query: textAfterAt.toLowerCase(),
    mentionStartPos: lastAtIndex,
    mentionEndPos: cursorPosition,
  };
};
