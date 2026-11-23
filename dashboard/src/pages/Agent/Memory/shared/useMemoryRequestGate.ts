import { useLayoutEffect, useMemo } from "react";
import { createDetailRequestGate } from "../../../../utils/detailRequestGate";

/** Own requests by a committed memory view, including repeated visits to it. */
export function useMemoryRequestGate(scopeKey: string) {
  const scope = useMemo(
    () => ({ scopeKey, active: false, gate: createDetailRequestGate() }),
    [scopeKey],
  );

  useLayoutEffect(() => {
    scope.active = true;
    return () => {
      scope.active = false;
      scope.gate.begin();
    };
  }, [scope]);

  return useMemo(
    () => ({
      isActive: () => scope.active,
      begin: () => {
        // An old mutation callback must not start a new request for its view.
        if (!scope.active) return null;
        const requestId = scope.gate.begin();
        return () => scope.active && scope.gate.isCurrent(requestId);
      },
    }),
    [scope],
  );
}
