import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import App from "./App";

// Stub page contents and providers; retain App's actual BrowserRouter/Routes.
vi.mock("./layouts/MainLayout", () => ({
  default: () => <div>console shell</div>,
}));
vi.mock("./pages/Chat/EmbeddedChat", async () => {
  const { useParams } = await import("react-router-dom");
  return {
    default: function EmbeddedPage() {
      const { agentId, threadId } = useParams();
      return (
        <div>
          embedded chat: {agentId}/{threadId ?? "new"}
        </div>
      );
    },
  };
});
vi.mock("./pages/Login", () => ({ default: () => null }));
vi.mock("./pages/Login/OidcComplete", () => ({ default: () => null }));
vi.mock("./pages/Setup", () => ({ default: () => null }));
vi.mock("./pages/Invite", () => ({ default: () => null }));
vi.mock("./components/AuthGuard", () => ({
  default: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./context/AgentContext", () => ({
  AgentProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./context/LayoutModeContext", () => ({
  LayoutModeProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./context/VoiceOutputContext", () => ({
  VoiceOutputProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock("./context/ThemeContext", () => ({
  ThemeProvider: ({ children }: { children: ReactNode }) => children,
  useTheme: () => ({ isDark: false, palette: "rose", customColor: "" }),
}));

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("App embedded routes", () => {
  it.each([
    ["/embed/chat/agent-a", "embedded chat: agent-a/new"],
    ["/embed/chat/agent-a/thr_1", "embedded chat: agent-a/thr_1"],
  ])("renders %s outside the console shell", (path, content) => {
    window.history.replaceState(null, "", path);
    render(<App />);
    expect(screen.getByText(content)).toBeInTheDocument();
    expect(screen.queryByText("console shell")).toBeNull();
    expect(screen.queryByText("common.notFound")).toBeNull();
  });

  it.each(["/embed/chat", "/embed/chat/agent-a/thr_1/extra"])(
    "renders the embedded 404 for %s outside the console shell",
    (path) => {
      window.history.replaceState(null, "", path);
      render(<App />);
      expect(screen.getByText("common.notFound")).toBeInTheDocument();
      expect(screen.queryByText("console shell")).toBeNull();
      expect(screen.queryByText(/embedded chat:/)).toBeNull();
    },
  );

  it("retains the console shell for normal chat routes", () => {
    window.history.replaceState(null, "", "/chat/agent-a/thr_1");
    render(<App />);
    expect(screen.getByText("console shell")).toBeInTheDocument();
  });
});
