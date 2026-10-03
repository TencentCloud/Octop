import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { UNAUTHORIZED_EVENT } from "../api/request";
import { chatLoginPath } from "../utils/chatRoute";

/**
 * Route an expired session to /login through the router.
 *
 * Claiming the event (``preventDefault``) keeps ``request.ts`` from doing a
 * full-page navigation, which would abort every in-flight lazy chunk and leave
 * the user staring at a blank page.
 */
export function useUnauthorizedRedirect(): void {
  const navigate = useNavigate();
  const location = useLocation();
  const loginPath = chatLoginPath(location);

  useEffect(() => {
    const handler = (event: Event) => {
      event.preventDefault();
      navigate(loginPath, { replace: true });
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, [navigate, loginPath]);
}
