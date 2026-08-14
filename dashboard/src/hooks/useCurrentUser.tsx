import {
  createContext,
  useContext,
  useMemo,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { OctopUser } from "../api/modules/auth";

type CurrentUserContextValue = {
  user: OctopUser | null;
  setUser: Dispatch<SetStateAction<OctopUser | null>>;
};

const CurrentUserContext = createContext<CurrentUserContextValue | null>(null);

export function CurrentUserProvider({
  user,
  setUser,
  children,
}: {
  user: OctopUser | null;
  setUser: Dispatch<SetStateAction<OctopUser | null>>;
  children: ReactNode;
}) {
  const value = useMemo(() => ({ user, setUser }), [user, setUser]);
  return (
    <CurrentUserContext.Provider value={value}>
      {children}
    </CurrentUserContext.Provider>
  );
}

/**
 * Current authenticated user from AuthGuard's ``/auth/me`` result.
 * ``null`` while loading or when the provider is not mounted.
 */
export function useCurrentUser(): OctopUser | null {
  return useContext(CurrentUserContext)?.user ?? null;
}

export function useSetCurrentUser(): Dispatch<
  SetStateAction<OctopUser | null>
> {
  const ctx = useContext(CurrentUserContext);
  if (!ctx) {
    return () => undefined;
  }
  return ctx.setUser;
}
