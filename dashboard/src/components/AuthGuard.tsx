import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Spin } from "antd";
import { clearAuthToken, getAuthToken } from "../api/request";
import { authApi, type OctopUser } from "../api/modules/auth";
import { applyUserLocale } from "../utils/locale";
import { isNetworkFetchError } from "../utils/networkError";
import { CurrentUserProvider } from "../hooks/useCurrentUser";
import BootOfflinePanel from "./BootOfflinePanel";

interface AuthGuardProps {
  children: React.ReactNode;
}

/**
 * Gate every protected route on (a) the initial admin existing and
 * (b) a valid JWT in localStorage. Octop always requires auth — there is
 * no "password protection disabled" mode like finnie had.
 *
 * Always wait for ``/api/setup/status`` (and ``/auth/me`` when a token
 * exists) before mounting children. Optimistic shell render with a stale
 * token would fire ``/api/agents`` / capabilities / update probes and get
 * 503'd by setup lockdown on first boot.
 *
 * When unauthenticated we must NOT render children: MainLayout / AgentProvider
 * would fire authenticated APIs, trip the 401 interceptor, and race the
 * navigate back to ``/login``.
 *
 * When the backend is unreachable (offline / Failed to fetch), show an
 * explicit offline panel with Retry instead of mounting a blank shell.
 */
export default function AuthGuard({ children }: AuthGuardProps) {
  const navigate = useNavigate();
  const [checking, setChecking] = useState(true);
  const [authed, setAuthed] = useState(false);
  const [user, setUser] = useState<OctopUser | null>(null);
  const [offline, setOffline] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      setOffline(false);
      setChecking(true);
      setAuthed(false);
      try {
        const status = await authApi.getAuthStatus();

        // No admin yet → push to setup wizard; drop any leftover JWT from a
        // previous install so background prefetch cannot stampede lockdown.
        if (status.setup_required) {
          clearAuthToken();
          if (!cancelled) navigate("/setup", { replace: true });
          return;
        }

        // Setup done. Need a token.
        const token = getAuthToken();
        if (!token) {
          if (!cancelled) {
            setAuthed(false);
            // Stay on the spinner until navigation away completes — do not
            // flip ``checking`` off or children would mount and 401→/login.
            navigate("/login", { replace: true });
          }
          return;
        }

        // Validate the token by hitting /auth/me. On 401 the request.ts
        // interceptor already kicks the user back to /login, so we just
        // need to swallow the throw here.
        try {
          const me = await authApi.me();
          await applyUserLocale(me.locale);
          if (!cancelled) {
            setUser(me);
            setAuthed(true);
            setChecking(false);
          }
        } catch (err) {
          if (cancelled) return;
          if (isNetworkFetchError(err)) {
            setOffline(true);
            setChecking(false);
            return;
          }
          setAuthed(false);
          navigate("/login", { replace: true });
        }
      } catch (err) {
        if (cancelled) return;
        // Backend unreachable (or setup/status otherwise failed) — do not
        // mount MainLayout with a null user (that produced a blank white
        // shell with no recovery action).
        void err;
        setOffline(true);
        setChecking(false);
      }
    };

    void check();
    return () => {
      cancelled = true;
    };
  }, [navigate, retryKey]);

  if (offline) {
    return (
      <BootOfflinePanel
        onRetry={() => {
          setRetryKey((k) => k + 1);
        }}
      />
    );
  }

  if (checking || !authed) {
    return (
      <div
        style={{
          height: "100dvh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--fn-bg-layout)",
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  return (
    <CurrentUserProvider user={user} setUser={setUser}>
      {children}
    </CurrentUserProvider>
  );
}
