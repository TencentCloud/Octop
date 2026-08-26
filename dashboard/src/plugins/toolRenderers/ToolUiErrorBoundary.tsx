import { Component, type ErrorInfo, type ReactNode } from "react";
import { BuiltinOctopUiFallback } from "./builtin/BuiltinOctopUiFallback";
import type { ToolRenderProps } from "./types";

interface State {
  error: Error | null;
}

/** Catch broken plugin renderers (bad jsx, missing React) and show fallback card. */
export class ToolUiErrorBoundary extends Component<
  { propsForFallback: ToolRenderProps; children: ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.warn("[plugin-ui] renderer crashed:", error, info.componentStack);
  }

  componentDidUpdate(prevProps: { propsForFallback: ToolRenderProps }): void {
    if (
      this.state.error &&
      prevProps.propsForFallback.output !== this.props.propsForFallback.output
    ) {
      this.setState({ error: null });
    }
  }

  render(): ReactNode {
    if (this.state.error) {
      return <BuiltinOctopUiFallback {...this.props.propsForFallback} />;
    }
    return this.props.children;
  }
}
