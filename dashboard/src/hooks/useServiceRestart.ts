import { useCallback, useEffect, useRef, useState } from "react";
import i18n from "../i18n";
import { probeHealth } from "../api/probeHealth";
import { updateApi } from "../api/modules/update";

import { message } from "@/utils/antdMessage";

const RESTART_POLL_TIMEOUT = 120_000;
const RESTART_POLL_INTERVAL = 800;
const RESTART_PROBE_TIMEOUT_MS = 2_000;
const RELOAD_DELAY_MS = 800;
/** Ignore early health OK while the old process is still shutting down. */
const MIN_WAIT_BEFORE_SUCCESS_MS = 3_000;
/** When health has no started_at (older backend), accept stable liveness after restart. */
const FALLBACK_WITHOUT_STARTED_AT_MS = 10_000;
const STABLE_ALIVE_POLLS = 4;

export type RestartPhase =
  | "idle"
  | "confirm"
  | "restarting"
  | "success"
  | "timeout";

/** True when the connection dropped or the service is temporarily unavailable. */
function shouldPollAfterRestartError(err: unknown): boolean {
  if (!(err instanceof Error)) {
    return false;
  }
  const msg = err.message;
  if (!msg.startsWith("Request failed:")) {
    return true;
  }
  const status = Number(/Request failed: (\d+)/.exec(msg)?.[1] ?? 0);
  return status === 502 || status === 503 || status === 504;
}

export function hasProcessRestarted(
  baselineStartedAt: number | undefined,
  currentStartedAt: number | undefined,
): boolean {
  return (
    baselineStartedAt != null &&
    currentStartedAt != null &&
    currentStartedAt !== baselineStartedAt
  );
}

export function useServiceRestart() {
  const [restartPhase, setRestartPhase] = useState<RestartPhase>("idle");
  const restartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const restartInFlightRef = useRef(false);
  const pollGenerationRef = useRef(0);

  const clearRestartTimer = useCallback(() => {
    if (restartTimerRef.current) {
      clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearRestartTimer();
      pollGenerationRef.current += 1;
    };
  }, [clearRestartTimer]);

  const resetRestart = useCallback(() => {
    pollGenerationRef.current += 1;
    clearRestartTimer();
    restartInFlightRef.current = false;
    setRestartPhase("idle");
  }, [clearRestartTimer]);

  const pollUntilAlive = useCallback(
    (
      deadline: number,
      restartAt: number,
      baselineStartedAt: number | undefined,
    ) => {
      const generation = pollGenerationRef.current;
      let sawDowntime = false;
      let consecutiveAlive = 0;

      const scheduleNext = () => {
        if (generation !== pollGenerationRef.current) {
          return;
        }
        restartTimerRef.current = setTimeout(
          () => void tick(),
          RESTART_POLL_INTERVAL,
        );
      };

      const tick = async () => {
        if (generation !== pollGenerationRef.current) {
          return;
        }
        if (Date.now() > deadline) {
          setRestartPhase("timeout");
          restartInFlightRef.current = false;
          return;
        }

        const probe = await probeHealth(RESTART_PROBE_TIMEOUT_MS);
        if (generation !== pollGenerationRef.current) {
          return;
        }

        if (!probe.ok) {
          sawDowntime = true;
          consecutiveAlive = 0;
          scheduleNext();
          return;
        }

        consecutiveAlive += 1;

        const waitedLongEnough =
          Date.now() - restartAt >= MIN_WAIT_BEFORE_SUCCESS_MS;
        const processRestarted = hasProcessRestarted(
          baselineStartedAt,
          probe.started_at,
        );
        const lacksStartedAt =
          baselineStartedAt == null && probe.started_at == null;
        const stableWithoutStartedAt =
          lacksStartedAt &&
          consecutiveAlive >= STABLE_ALIVE_POLLS &&
          Date.now() - restartAt >= FALLBACK_WITHOUT_STARTED_AT_MS;
        if (
          waitedLongEnough &&
          (processRestarted ||
            (sawDowntime && probe.ok) ||
            stableWithoutStartedAt)
        ) {
          setRestartPhase("success");
          restartInFlightRef.current = false;
          restartTimerRef.current = setTimeout(
            () => window.location.reload(),
            RELOAD_DELAY_MS,
          );
          return;
        }

        scheduleNext();
      };

      void tick();
    },
    [],
  );

  const executeRestart = useCallback(async () => {
    if (restartInFlightRef.current) {
      return;
    }
    restartInFlightRef.current = true;
    pollGenerationRef.current += 1;
    clearRestartTimer();
    setRestartPhase("restarting");
    const restartAt = Date.now();
    const baseline = await probeHealth(RESTART_PROBE_TIMEOUT_MS);
    const baselineStartedAt = baseline.started_at;
    try {
      await updateApi.restartService();
    } catch (err) {
      if (!shouldPollAfterRestartError(err)) {
        restartInFlightRef.current = false;
        setRestartPhase("idle");
        message.error(i18n.t("advancedSettings.update.restartFailed"));
        return;
      }
    }
    pollUntilAlive(
      Date.now() + RESTART_POLL_TIMEOUT,
      restartAt,
      baselineStartedAt,
    );
  }, [clearRestartTimer, pollUntilAlive]);

  const requestRestart = useCallback(() => {
    if (restartInFlightRef.current) {
      return;
    }
    setRestartPhase("confirm");
  }, []);

  const isRestarting = restartPhase === "restarting";

  return {
    restartPhase,
    isRestarting,
    requestRestart,
    executeRestart,
    resetRestart,
  };
}
