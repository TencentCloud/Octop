import { lazy, Suspense } from "react";
import AuthGuard from "../../components/AuthGuard";
import PageLoading from "../../components/PageLoading";
import { AgentProvider } from "../../context/AgentContext";
import { VoiceOutputProvider } from "../../context/VoiceOutputContext";

const Chat = lazy(() => import("./index"));

export default function EmbeddedChat() {
  return (
    <AuthGuard>
      <AgentProvider>
        <VoiceOutputProvider>
          <div
            style={{
              height: "100%",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
            }}
          >
            <Suspense fallback={<PageLoading />}>
              <Chat />
            </Suspense>
          </div>
        </VoiceOutputProvider>
      </AgentProvider>
    </AuthGuard>
  );
}
