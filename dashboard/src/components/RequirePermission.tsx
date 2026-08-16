import { Spin } from "antd";
import { useLocation } from "react-router-dom";
import { useCurrentUser } from "../hooks/useCurrentUser";
import { canAccessPath } from "../utils/permissions";
import ForbiddenPage from "./ForbiddenPage";

interface Props {
  children: React.ReactNode;
}

/**
 * Wraps routes that have a module permission (or admin-only paths).
 * Shows a spinner while /auth/me is loading, and a permission-denied
 * page when the current user cannot access the path.
 */
export default function RequirePermission({ children }: Props) {
  const user = useCurrentUser();
  const location = useLocation();

  if (user === null) {
    return (
      <div
        style={{
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (!canAccessPath(user, location.pathname)) {
    return <ForbiddenPage />;
  }

  return <>{children}</>;
}
