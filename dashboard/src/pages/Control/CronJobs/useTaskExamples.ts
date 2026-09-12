import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { agentChatApi } from "../../../api/modules/agentChat";
import type { CronTaskExamples } from "../../../api/modules/cronjob";
import { normalizeUiLocale } from "../../../utils/locale";
import { resolveTaskExamples } from "./taskExamples";

export function useTaskExamples(agentId: string | null): string[] {
  const { t, i18n } = useTranslation();
  const locale = normalizeUiLocale(i18n.language);
  const defaults = useMemo(
    () => [
      t("cronJobs.noJobsSuggestion1"),
      t("cronJobs.noJobsSuggestion2"),
      t("cronJobs.noJobsSuggestion3"),
    ],
    [t],
  );
  const cacheRef = useRef(new Map<string, CronTaskExamples | null>());
  const [payload, setPayload] = useState<CronTaskExamples | null | undefined>(
    undefined,
  );

  useEffect(() => {
    let cancelled = false;
    if (!agentId) {
      setPayload(undefined);
      return;
    }
    if (cacheRef.current.has(agentId)) {
      setPayload(cacheRef.current.get(agentId));
    } else {
      setPayload(undefined);
    }

    void agentChatApi
      .welcome(agentId)
      .then((data) => {
        if (cancelled) return;
        const next = data.task_examples ?? null;
        cacheRef.current.set(agentId, next);
        setPayload(next);
      })
      .catch(() => {
        if (cancelled || cacheRef.current.has(agentId)) return;
        cacheRef.current.set(agentId, null);
        setPayload(null);
      });

    return () => {
      cancelled = true;
    };
  }, [agentId]);

  return useMemo(() => {
    if (payload === undefined) return [];
    return resolveTaskExamples(payload, locale, defaults);
  }, [payload, locale, defaults]);
}
