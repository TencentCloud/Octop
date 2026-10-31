import { useEffect, useState } from "react";
import { request } from "../../../api/request";

export interface NamedStorageBackend {
  name: string;
  kind: string;
}

/** One in-flight list shared by every expert card and table row. */
let inflight: Promise<NamedStorageBackend[]> | null = null;

export function loadNamedStorageBackends(): Promise<NamedStorageBackend[]> {
  if (!inflight) {
    inflight = request<NamedStorageBackend[]>("/storage-backends")
      .then((rows) => (Array.isArray(rows) ? rows : []))
      .catch(() => [] as NamedStorageBackend[])
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

export function useNamedStorageBackends(): NamedStorageBackend[] {
  const [rows, setRows] = useState<NamedStorageBackend[]>([]);

  useEffect(() => {
    let cancelled = false;
    void loadNamedStorageBackends().then((next) => {
      if (!cancelled) setRows(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return rows;
}
