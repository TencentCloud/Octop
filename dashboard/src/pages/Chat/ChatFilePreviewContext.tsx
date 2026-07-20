import { createContext, useContext, type ReactNode } from "react";

interface ChatFilePreviewContextValue {
  /** Open the shared file panel on a workspace path (preview / download cards). */
  openFilePreview: (path: string) => void;
}

const ChatFilePreviewContext =
  createContext<ChatFilePreviewContextValue | null>(null);

export function ChatFilePreviewProvider({
  openFilePreview,
  children,
}: {
  openFilePreview: (path: string) => void;
  children: ReactNode;
}) {
  return (
    <ChatFilePreviewContext.Provider value={{ openFilePreview }}>
      {children}
    </ChatFilePreviewContext.Provider>
  );
}

export function useChatFilePreview(): ChatFilePreviewContextValue | null {
  return useContext(ChatFilePreviewContext);
}
