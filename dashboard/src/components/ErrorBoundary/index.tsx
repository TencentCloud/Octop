import { Component, type ReactNode } from "react";
import { Result, Button, Space } from "antd";
import i18n from "../../i18n";
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
              isChunkError
                ? i18n.t("errors.outOfDateTitle")
                : i18n.t("errors.unexpectedTitle")
            }
            subTitle={
              isChunkError
                ? i18n.t("errors.outOfDateSubtitle")
                : this.state.error?.message ||
                  i18n.t("errors.unexpectedSubtitle")
            }
            extra={
              <Space>
                {isChunkError && (
                  <Button type="primary" onClick={this.handleReload}>
                    {i18n.t("errors.reload")}
                  </Button>
                )}
                {canRetry && (
                  <Button type="primary" onClick={this.handleRetry}>
                    {i18n.t("errors.retry")}
                  </Button>
                )}
                <Button onClick={this.handleHome}>
                  {i18n.t("errors.backHome")}
                </Button>
              </Space>
            }
          />
        </div>
      );
    }
    return this.props.children;
  }
}
