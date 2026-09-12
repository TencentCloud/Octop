import { createContext, useContext, useMemo, type ReactNode } from "react";

interface ChatAgentProfileContextValue {
  openAgentProfile: () => void;
  canOpen: boolean;
}

const ChatAgentProfileContext =
  createContext<ChatAgentProfileContextValue | null>(null);

export function ChatAgentProfileProvider({
  canOpen,
  onOpen,
  children,
}: {
  canOpen: boolean;
  onOpen: () => void;
  children: ReactNode;
}) {
  const value = useMemo(
    () => ({
      canOpen,
      openAgentProfile: onOpen,
    }),
    [canOpen, onOpen],
  );
  return (
    <ChatAgentProfileContext.Provider value={value}>
      {children}
    </ChatAgentProfileContext.Provider>
  );
}

export function useChatAgentProfile(): ChatAgentProfileContextValue | null {
  return useContext(ChatAgentProfileContext);
}
