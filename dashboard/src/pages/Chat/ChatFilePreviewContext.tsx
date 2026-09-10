import { createContext, useContext, type ReactNode } from "react";
import type { KnowledgeCitation } from "../../utils/parseKnowledgeCitations";

interface ChatFilePreviewContextValue {
  /** Open the shared file panel on a workspace path (preview / download cards). */
  openFilePreview: (path: string) => void;
  /** Open a knowledge citation in the shared chat dock (same shell as file tabs). */
  openKnowledgeCitation: (citation: KnowledgeCitation) => void;
}

const ChatFilePreviewContext =
  createContext<ChatFilePreviewContextValue | null>(null);

export function ChatFilePreviewProvider({
  openFilePreview,
  openKnowledgeCitation,
  children,
}: {
  openFilePreview: (path: string) => void;
  openKnowledgeCitation: (citation: KnowledgeCitation) => void;
  children: ReactNode;
}) {
  return (
    <ChatFilePreviewContext.Provider
      value={{ openFilePreview, openKnowledgeCitation }}
    >
      {children}
    </ChatFilePreviewContext.Provider>
  );
}

export function useChatFilePreview(): ChatFilePreviewContextValue | null {
  return useContext(ChatFilePreviewContext);
}
