import { createContext, useContext, useMemo, type ReactNode } from "react";

interface ChatAgentProfileContextValue {
  openAgentProfile: (agentId?: string) => void;
  canOpen: boolean;
  isTeam: boolean;
}

const ChatAgentProfileContext =
  createContext<ChatAgentProfileContextValue | null>(null);

export function ChatAgentProfileProvider({
  canOpen,
  onOpen,
  isTeam = false,
  children,
}: {
  canOpen: boolean;
  onOpen: (agentId?: string) => void;
  isTeam?: boolean;
  children: ReactNode;
}) {
  const value = useMemo(
    () => ({
      canOpen,
      isTeam,
      openAgentProfile: onOpen,
    }),
    [canOpen, isTeam, onOpen],
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
