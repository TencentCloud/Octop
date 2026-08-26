import { useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
import TerminalView, {
  type TerminalViewHandle,
} from "../Terminal/components/TerminalView";
import { getTerminalTheme } from "../Terminal/terminalThemes";
import { useTheme } from "../../../context/ThemeContext";
import { useAdbShell } from "./useAdbShell";
import styles from "./AdbShellPanel.module.less";

type AdbShellPanelProps = {
  device: string;
  /** Stream is up — same device serial is already selected. */
  streamActive: boolean;
  visible: boolean;
  /** Shown when the stream is not connected (same guide as the Screen tab). */
  idleGuide?: ReactNode;
};

export default function AdbShellPanel({
  device,
  streamActive,
  visible,
  idleGuide,
}: AdbShellPanelProps) {
  const { isDark } = useTheme();
  const terminalRef = useRef<TerminalViewHandle | null>(null);
  const connectedRef = useRef(false);
  const sizeRef = useRef({ cols: 120, rows: 32 });
  const { connect, disconnect, sendInput, sendResize } = useAdbShell();

  const themeDefinition = useMemo(
    () => getTerminalTheme(null, isDark),
    [isDark],
  );

  const shellEnabled = visible && Boolean(device) && streamActive;

  const handleResize = useCallback(
    (cols: number, rows: number) => {
      sizeRef.current = { cols, rows };
      sendResize(cols, rows);
    },
    [sendResize],
  );

  const handleTerminalReady = useCallback(() => {
    if (!shellEnabled || connectedRef.current || !device) return;
    connectedRef.current = true;
    terminalRef.current?.fit();
    const { cols, rows } = sizeRef.current;
    connect(device, {
      cols,
      rows,
      onOutput: (data) => terminalRef.current?.write(data),
      onError: (message) => terminalRef.current?.write(`\r\n[${message}]\r\n`),
    });
  }, [connect, device, shellEnabled]);

  useEffect(() => {
    if (!shellEnabled) {
      connectedRef.current = false;
      disconnect();
      terminalRef.current?.reset();
      return;
    }
    return () => {
      connectedRef.current = false;
      disconnect();
    };
  }, [disconnect, shellEnabled]);

  // Re-fit after the split pane finishes opening (display:none → flex).
  useEffect(() => {
    if (!shellEnabled || !visible) return;
    const timer = window.setTimeout(() => {
      terminalRef.current?.fit();
    }, 80);
    return () => window.clearTimeout(timer);
  }, [shellEnabled, visible]);

  return (
    <div className={styles.root}>
      {!streamActive ? (
        <div className={styles.idleFill}>{idleGuide}</div>
      ) : (
        <div
          className={styles.terminalWrap}
          style={{
            backgroundColor: themeDefinition.theme.background as string,
          }}
        >
          <TerminalView
            terminalRef={terminalRef}
            themeDefinition={themeDefinition}
            onData={sendInput}
            onResize={handleResize}
            onReady={handleTerminalReady}
          />
        </div>
      )}
    </div>
  );
}
