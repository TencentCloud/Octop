import { Component, type ReactNode } from "react";
import i18n from "../../i18n";
import {
  isChunkLoadError,
  tryReloadOnStaleChunk,
} from "../../utils/reloadOnStaleChunk";
import ErrorFallback, { type ErrorFallbackAction } from "./ErrorFallback";

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
      // A stale chunk has one honest fix (reload); an unexpected throw offers
      // "try again" first, because a re-render is often all it takes.
      const actions: ErrorFallbackAction[] = [];
      if (isChunkError) {
        actions.push({
          label: i18n.t("errors.reload"),
          onClick: this.handleReload,
          variant: "primary",
        });
      }
      if (canRetry) {
        actions.push({
          label: i18n.t("errors.retry"),
          onClick: this.handleRetry,
          variant: "primary",
        });
      }
      actions.push({
        label: i18n.t("errors.backHome"),
        onClick: this.handleHome,
      });
      return (
        <ErrorFallback
          title={
            isChunkError
              ? i18n.t("errors.outOfDateTitle")
              : i18n.t("errors.unexpectedTitle")
          }
          subtitle={
            isChunkError
              ? i18n.t("errors.outOfDateSubtitle")
              : i18n.t("errors.unexpectedSubtitle")
          }
          detail={isChunkError ? null : this.state.error?.message}
          detailsLabel={i18n.t("errors.details")}
          actions={actions}
        />
      );
    }
    return this.props.children;
  }
}
