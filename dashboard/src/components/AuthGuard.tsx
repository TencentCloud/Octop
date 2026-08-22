import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Spin } from "antd";
import { getAuthToken } from "../api/request";
import { authApi, type OctopUser } from "../api/modules/auth";
import { applyUserLocale } from "../utils/locale";
import { CurrentUserProvider } from "../hooks/useCurrentUser";

interface AuthGuardProps {
  children: React.ReactNode;
}

function inviteRedirectTarget(searchParams: URLSearchParams): string | null {
  const invite = (
    searchParams.get("invite") ||
    searchParams.get("code") ||
    ""
  ).trim();
  if (!invite) return null;
  return `/invite?code=${encodeURIComponent(invite)}`;
}

/**
 * Gate every protected route on (a) the initial admin existing and
 * (b) a valid JWT in localStorage. Octop always requires auth — there is
 * no "password protection disabled" mode like finnie had.
 *
 * Auth is checked once on mount (not on every pathname change). When a JWT
 * is already present we render the shell immediately and validate in the
 * background — a full-page Spin on every hard refresh feels like the app
 * is "reloading" even though routing did not change.
 *
 * When unauthenticated we must NOT render children: MainLayout / AgentProvider
 * would fire authenticated APIs, trip the 401 interceptor, and race the
 * invite redirect back to ``/login``.
 */
export default function AuthGuard({ children }: AuthGuardProps) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const hadToken = Boolean(getAuthToken());
  const [checking, setChecking] = useState(!hadToken);
  const [authed, setAuthed] = useState(hadToken);
  const [user, setUser] = useState<OctopUser | null>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const status = await authApi.getAuthStatus();

        // No admin yet → push to setup wizard.
        if (status.setup_required) {
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
            const inviteTo = inviteRedirectTarget(searchParams);
            navigate(inviteTo ?? "/login", { replace: true });
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
        } catch {
          if (!cancelled) {
            setAuthed(false);
            navigate("/login", { replace: true });
          }
        }
      } catch {
        // Backend unreachable — let the user through. The next API call
        // will surface the real error if the network is broken.
        if (!cancelled) {
          setAuthed(true);
          setChecking(false);
        }
      }
    };

    void check();
    return () => {
      cancelled = true;
    };
  }, [navigate, searchParams]);

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
