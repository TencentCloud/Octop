/**
 * useStorageBackends — admin storage backend management hook + type definitions.
 */
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Database,
  HardDrive,
  Server,
  Folder,
  Terminal,
  Globe,
  Archive,
  Package,
  Container,
} from "lucide-react";
import { request } from "../../../api/request";

export interface StorageBackendRow {
  id: number;
  name: string;
  kind: string;
  endpoint: string | null;
  /** Masked on the server — first 4 chars + asterisks. */
  access_key: string | null;
  bucket: string | null;
  region: string | null;
  config_json: string | null;
  note: string | null;
  enabled: boolean;
  /** Admin storage browse only (``/admin/backend``); expert workspace is always available. */
  previewable?: boolean;
  created_at: number;
  updated_at: number;
}

/** Field descriptor for a single form field in a StorageTypeDef */
export interface StorageFieldDef {
  key: string;
  /** i18n key for the label, e.g. "storage.accessKeyLabel" */
  labelKey: string;
  /** i18n key for required-field validation (defaults by ``key`` when omitted). */
  requiredMessageKey?: string;
  required?: boolean;
  secret?: boolean;
  placeholder?: string;
  type?: "text" | "password" | "number" | "textarea" | "switch";
}

/** Kinds that map to a harness backend spec. */
export const AGENT_RESOLVABLE_STORAGE_KINDS = new Set([
  "cos",
  "s3",
  "oss",
  "obs",
  "custom",
  "filesystem",
  "shell",
  "postgres",
  "docker",
]);

export function isAgentResolvableStorageKind(kind: string): boolean {
  return AGENT_RESOLVABLE_STORAGE_KINDS.has(kind.toLowerCase());
}

/** Definition of a preset storage backend type shown in the supported-types tab. */
export interface StorageTypeDef {
  kind: string;
  /** i18n key for the display name */
  nameKey: string;
  /** i18n key for the description */
  descKey: string;
  /** accent color for the card */
  color: string;
  /** lucide-react icon node */
  icon: ReactNode;
  /** ordered list of form fields relevant to this type */
  fields: StorageFieldDef[];
}

export const STORAGE_TYPE_DEFS: StorageTypeDef[] = [
  {
    kind: "cos",
    nameKey: "storage.kindCos",
    descKey: "storage.descCos",
    color: "#0052d9",
    icon: <Package size={20} />,
    fields: [
      {
        key: "access_key",
        labelKey: "storage.accessKeyLabel",
        required: true,
        secret: false,
        placeholder: "AKIDxxx",
      },
      {
        key: "secret_key",
        labelKey: "storage.secretKeyLabel",
        required: true,
        secret: true,
        placeholder: "SKEYxxx",
      },
      {
        key: "bucket",
        labelKey: "storage.bucketLabel",
        required: true,
        placeholder: "my-bucket-1250000000",
      },
      {
        key: "region",
        labelKey: "storage.regionLabel",
        required: true,
        placeholder: "ap-guangzhou",
      },
      {
        key: "endpoint",
        labelKey: "storage.endpointLabel",
        placeholder: "cos.ap-guangzhou.myqcloud.com",
      },
    ],
  },
  {
    kind: "s3",
    nameKey: "storage.kindS3",
    descKey: "storage.descS3",
    color: "#ff9900",
    icon: <Archive size={20} />,
    fields: [
      {
        key: "access_key",
        labelKey: "storage.accessKeyLabel",
        required: true,
        placeholder: "AKIAxxx",
      },
      {
        key: "secret_key",
        labelKey: "storage.secretKeyLabel",
        required: true,
        secret: true,
        placeholder: "xxxxxxxx",
      },
      {
        key: "bucket",
        labelKey: "storage.bucketLabel",
        required: true,
        placeholder: "my-bucket",
      },
      {
        key: "region",
        labelKey: "storage.regionLabel",
        required: true,
        placeholder: "us-east-1",
      },
      {
        key: "endpoint",
        labelKey: "storage.endpointLabel",
        placeholder: "s3.us-east-1.amazonaws.com",
      },
    ],
  },
  {
    kind: "oss",
    nameKey: "storage.kindOss",
    descKey: "storage.descOss",
    color: "#ff6a00",
    icon: <HardDrive size={20} />,
    fields: [
      {
        key: "access_key",
        labelKey: "storage.accessKeyLabel",
        required: true,
        placeholder: "LTAIxxx",
      },
      {
        key: "secret_key",
        labelKey: "storage.secretKeyLabel",
        required: true,
        secret: true,
        placeholder: "xxxxxxxx",
      },
      {
        key: "bucket",
        labelKey: "storage.bucketLabel",
        required: true,
        placeholder: "my-bucket",
      },
      {
        key: "region",
        labelKey: "storage.regionLabel",
        required: true,
        placeholder: "oss-cn-hangzhou",
      },
      {
        key: "endpoint",
        labelKey: "storage.endpointLabel",
        placeholder: "oss-cn-hangzhou.aliyuncs.com",
      },
    ],
  },
  {
    kind: "obs",
    nameKey: "storage.kindObs",
    descKey: "storage.descObs",
    color: "#c7000b",
    icon: <Server size={20} />,
    fields: [
      {
        key: "access_key",
        labelKey: "storage.accessKeyLabel",
        required: true,
        placeholder: "AKxxx",
      },
      {
        key: "secret_key",
        labelKey: "storage.secretKeyLabel",
        required: true,
        secret: true,
        placeholder: "xxxxxxxx",
      },
      {
        key: "bucket",
        labelKey: "storage.bucketLabel",
        required: true,
        placeholder: "my-bucket",
      },
      {
        key: "region",
        labelKey: "storage.regionLabel",
        required: true,
        placeholder: "cn-north-4",
      },
      {
        key: "endpoint",
        labelKey: "storage.endpointLabel",
        placeholder: "obs.cn-north-4.myhuaweicloud.com",
      },
    ],
  },
  {
    kind: "filesystem",
    nameKey: "storage.kindFilesystem",
    descKey: "storage.descFilesystem",
    color: "#52c41a",
    icon: <Folder size={20} />,
    fields: [
      {
        key: "bucket",
        labelKey: "storage.rootDirLabel",
        requiredMessageKey: "storage.pleaseEnterRootDir",
        required: true,
        placeholder: "/data/agent-workspace",
      },
    ],
  },
  {
    kind: "shell",
    nameKey: "storage.kindShell",
    descKey: "storage.descShell",
    color: "#722ed1",
    icon: <Terminal size={20} />,
    fields: [
      {
        key: "bucket",
        labelKey: "storage.rootDirLabel",
        requiredMessageKey: "storage.pleaseEnterRootDir",
        required: true,
        placeholder: "/workspace",
      },
      { key: "region", labelKey: "storage.timeoutLabel", placeholder: "120" },
    ],
  },
  {
    kind: "docker",
    nameKey: "storage.kindDocker",
    descKey: "storage.descDocker",
    color: "#2496ed",
    icon: <Container size={20} />,
    fields: [
      {
        key: "bucket",
        labelKey: "storage.dockerImageLabel",
        requiredMessageKey: "storage.pleaseEnterDockerImage",
        required: true,
        placeholder: "python:3.12-slim",
      },
    ],
  },
  {
    kind: "postgres",
    nameKey: "storage.kindPostgres",
    descKey: "storage.descPostgres",
    color: "#336791",
    icon: <Database size={20} />,
    fields: [
      {
        key: "endpoint",
        labelKey: "storage.hostLabel",
        requiredMessageKey: "storage.pleaseEnterHost",
        required: true,
        placeholder: "localhost:5432",
      },
      {
        key: "access_key",
        labelKey: "storage.dbUserLabel",
        requiredMessageKey: "storage.pleaseEnterDbUser",
        required: true,
        placeholder: "postgres",
      },
      {
        key: "secret_key",
        labelKey: "storage.dbPasswordLabel",
        requiredMessageKey: "storage.pleaseEnterDbPassword",
        required: true,
        secret: true,
        placeholder: "••••••••",
      },
      {
        key: "bucket",
        labelKey: "storage.dbNameLabel",
        requiredMessageKey: "storage.pleaseEnterDbName",
        required: true,
        placeholder: "mydb",
      },
      {
        key: "region",
        labelKey: "storage.dbSchemaLabel",
        placeholder: "public",
      },
    ],
  },
  {
    kind: "custom",
    nameKey: "storage.kindCustom",
    descKey: "storage.descCustom",
    color: "#8c8c8c",
    icon: <Globe size={20} />,
    fields: [
      {
        key: "endpoint",
        labelKey: "storage.endpointLabel",
        placeholder: "https://...",
      },
      {
        key: "access_key",
        labelKey: "storage.accessKeyLabel",
        placeholder: "AKxxx",
      },
      {
        key: "secret_key",
        labelKey: "storage.secretKeyLabel",
        secret: true,
        placeholder: "SKxxx",
      },
      {
        key: "bucket",
        labelKey: "storage.bucketLabel",
        placeholder: "my-bucket",
      },
      {
        key: "region",
        labelKey: "storage.regionLabel",
        placeholder: "us-east-1",
      },
    ],
  },
];

export const STORAGE_KINDS = STORAGE_TYPE_DEFS.map((t) => ({
  value: t.kind,
  labelKey: t.nameKey,
}));

export interface UseStorageBackendsResult {
  backends: StorageBackendRow[];
  loading: boolean;
  error: string | null;
  fetchAll: () => Promise<void>;
}

export function useStorageBackends(): UseStorageBackendsResult {
  const [backends, setBackends] = useState<StorageBackendRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rows = await request<StorageBackendRow[]>(
        "/admin/storage-backends",
      );
      setBackends(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载存储后端失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  return { backends, loading, error, fetchAll };
}
