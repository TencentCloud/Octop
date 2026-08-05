import { Component, type ReactNode } from "react";
import { Result, Button, Space } from "antd";
import {
  isChunkLoadError,
  tryReloadOnStaleChunk,
} from "../../utils/reloadOnStaleChunk";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  retryCount: number;
  /** ``null`` until componentDidCatch has decided whether a reload is coming. */
  chunkReloading: boolean | null;
}

const MAX_RETRIES = 3;

/**
 * Global error boundary — catches unhandled errors in the React tree
 * and displays a friendly fallback UI with retry / home actions.
 */
export default class GlobalErrorBoundary extends Component<Props, State> {
  state: State = {
    hasError: false,
    error: null,
    retryCount: 0,
    chunkReloading: null,
  };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error, chunkReloading: null };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    if (tryReloadOnStaleChunk(error)) {
      this.setState({ chunkReloading: true });
      return;
    }
    this.setState({ chunkReloading: false });
    console.error("[GlobalErrorBoundary]", error, info.componentStack);
  }

  handleRetry = () => {
    if (this.state.retryCount >= MAX_RETRIES) return;
    this.setState((prev) => ({
      hasError: false,
      error: null,
      chunkReloading: null,
      retryCount: prev.retryCount + 1,
    }));
  };

  handleHome = () => {
    window.location.href = "/chat";
  };

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      const isChunkError = isChunkLoadError(this.state.error);
      // Stale chunk → silent soft reload; avoid flashing the error page.
      if (isChunkError && this.state.chunkReloading !== false) {
        return null;
      }
      const canRetry = !isChunkError && this.state.retryCount < MAX_RETRIES;
      return (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            minHeight: "100dvh",
          }}
        >
          <Result
            status="error"
            title={
              isChunkError ? "This page is out of date" : "Something went wrong"
            }
            subTitle={
              isChunkError
                ? "The app was updated while this tab was open. Reload to continue."
                : this.state.error?.message || "An unexpected error occurred."
            }
            extra={
              <Space>
                {isChunkError && (
                  <Button type="primary" onClick={this.handleReload}>
                    Reload
                  </Button>
                )}
                {canRetry && (
                  <Button type="primary" onClick={this.handleRetry}>
                    Retry
                  </Button>
                )}
                <Button onClick={this.handleHome}>Back to Home</Button>
              </Space>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}
