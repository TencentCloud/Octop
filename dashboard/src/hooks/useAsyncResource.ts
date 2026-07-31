import { useCallback, useEffect, useRef, useState } from "react";
import type { TFunction } from "i18next";
import { apiErrorMessage } from "../utils/apiError";

import { message } from "@/utils/antdMessage";

export interface UseAsyncResourceOptions {
  /** When false, skips fetch and resets to initialValue. */
  enabled?: boolean;
  errorFallback?: string;
  t?: TFunction;
  logLabel?: string;
}

export function useAsyncResource<T>(
  initialValue: T,
  fetcher: () => Promise<T>,
  deps: React.DependencyList,
  options?: UseAsyncResourceOptions,
): {
  data: T;
  loading: boolean;
  refresh: () => Promise<void>;
  setData: React.Dispatch<React.SetStateAction<T>>;
} {
  const [data, setData] = useState<T>(initialValue);
  const [loading, setLoading] = useState(false);
  const initialRef = useRef(initialValue);
  initialRef.current = initialValue;
  const enabled = options?.enabled !== false;

  const refresh = useCallback(async () => {
    if (!enabled) {
      setData(initialRef.current);
      return;
    }
    setLoading(true);
    try {
      setData(await fetcher());
    } catch (error) {
      if (options?.logLabel) {
        console.error(`[${options.logLabel}]`, error);
      } else {
        console.error(error);
      }
      if (options?.errorFallback) {
        message.error(apiErrorMessage(error, options.errorFallback, options.t));
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, refresh, setData };
}
