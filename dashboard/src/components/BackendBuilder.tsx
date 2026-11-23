/**
 * BackendBuilder — visual editor for octop-harness backend specs.
 *
 * The octop-harness backend system supports several types
 * (local_shell, filesystem, state, store, s3, cos, postgres) and a
 * special ``composite`` type that routes by path-prefix to nested
 * sub-backends. This component lets the user pick one of:
 *
 *   1. Independent — a single backend of any built-in type
 *   2. Composite   — a default sub-backend + N route entries
 *
 * The output is a JSON-serializable spec ready to be sent in
 * ``POST /api/agents`` as ``config.backend``. The backend itself
 * accepts both string aliases (``"local_shell"``) and dicts
 * (``{type, root_dir, …}``); we always emit a dict so the surface
 * is uniform.
 *
 * Composite nesting is intentionally **one level only**: nested
 * composites are technically legal in octop-harness but rare in
 * practice, and an unconstrained tree editor is hard to use without
 * dedicated UX. The JSON preview at the bottom is read-only, so nested
 * composites cannot be authored in this builder.
 */

import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { Trash2, Plus, Info } from "lucide-react";

const { Text } = Typography;

export type BackendKind =
  | "local_shell"
  | "filesystem"
  | "state"
  | "store"
  | "s3"
  | "cos"
  | "postgres";

interface IndependentSpec {
  type: BackendKind;
  // Local-class kwargs
  root_dir?: string;
  // Remote object-store kwargs
  bucket?: string;
  endpoint_url?: string;
  region?: string;
  addressing_style?: "virtual" | "path";
  // Postgres kwargs
  connection_string?: string;
  // Free-form passthrough for fields we don't model yet
  [k: string]: unknown;
}

interface RouteEntry {
  prefix: string;
  spec: IndependentSpec;
}

interface CompositeSpec {
  type: "composite";
  default: IndependentSpec;
  routes: Record<string, IndependentSpec>;
}

export type BackendSpec = IndependentSpec | CompositeSpec;

interface BackendBuilderProps {
  /** Initial value; the field can be omitted in which case the default is used. */
  value?: BackendSpec | null;
  onChange?: (spec: BackendSpec) => void;
}

const KIND_OPTIONS: { value: BackendKind; label: string; hint: string }[] = [
  {
    value: "local_shell",
    label: "Local shell",
    hint: "本机 shell + 文件系统(完全访问主机)",
  },
  {
    value: "filesystem",
    label: "Filesystem",
    hint: "受限本机文件系统(只在 root_dir 下读写)",
  },
  { value: "state", label: "State (in-memory)", hint: "进程内状态,重启即失效" },
  { value: "store", label: "Store (kv)", hint: "key-value 存储,适合临时数据" },
  {
    value: "s3",
    label: "S3 / object storage",
    hint: "AWS S3 / 兼容 S3 协议的对象存储",
  },
  {
    value: "cos",
    label: "Tencent Cloud COS",
    hint: "腾讯云 COS(基于 S3 协议)",
  },
  { value: "postgres", label: "Postgres", hint: "Postgres 数据库后端" },
];

function defaultIndependent(): IndependentSpec {
  return { type: "local_shell", root_dir: "/" };
}

function defaultComposite(): CompositeSpec {
  return {
    type: "composite",
    default: defaultIndependent(),
    routes: {},
  };
}

function IndependentEditor({
  value,
  onChange,
  compact,
}: {
  value: IndependentSpec;
  onChange: (next: IndependentSpec) => void;
  compact?: boolean;
}) {
  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const opt = KIND_OPTIONS.find((o) => o.value === value.type);
  const labelStyle = { fontSize: 12, color: "var(--fn-text-tertiary)" };
  const blockStyle: React.CSSProperties = compact
    ? { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }
    : { display: "flex", flexDirection: "column", gap: 8 };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div>
        <div style={labelStyle}>Type</div>
        <Select
          value={value.type}
          onChange={(t) => onChange({ type: t as BackendKind })}
          style={{ width: "100%" }}
          options={KIND_OPTIONS.map((o) => ({
            value: o.value,
            label: (
              <Space size={6}>
                <span>{o.label}</span>
                <Tooltip title={o.hint}>
                  <Info size={12} color="var(--fn-text-tertiary)" />
                </Tooltip>
              </Space>
            ),
          }))}
        />
        {opt && <div style={{ ...labelStyle, marginTop: 4 }}>{opt.hint}</div>}
      </div>

      <div style={blockStyle}>
        {(value.type === "local_shell" || value.type === "filesystem") && (
          <div>
            <div style={labelStyle}>root_dir</div>
            <Input
              value={value.root_dir ?? ""}
              onChange={(e) => setField("root_dir", e.target.value)}
              placeholder="/"
            />
          </div>
        )}
        {(value.type === "s3" || value.type === "cos") && (
          <>
            <div>
              <div style={labelStyle}>bucket</div>
              <Input
                value={value.bucket ?? ""}
                onChange={(e) => setField("bucket", e.target.value)}
                placeholder="my-bucket"
              />
            </div>
            <div>
              <div style={labelStyle}>region</div>
              <Input
                value={value.region ?? ""}
                onChange={(e) => setField("region", e.target.value)}
                placeholder={value.type === "cos" ? "ap-shanghai" : "us-east-1"}
              />
            </div>
            <div>
              <div style={labelStyle}>endpoint_url (optional)</div>
              <Input
                value={value.endpoint_url ?? ""}
                onChange={(e) => setField("endpoint_url", e.target.value)}
                placeholder={
                  value.type === "cos"
                    ? "https://cos.<region>.myqcloud.com"
                    : "https://s3.amazonaws.com"
                }
              />
            </div>
            <div>
              <div style={labelStyle}>addressing_style</div>
              <Select
                value={value.addressing_style ?? "virtual"}
                onChange={(v) => setField("addressing_style", v)}
                style={{ width: "100%" }}
                options={[
                  { value: "virtual", label: "virtual (recommended)" },
                  { value: "path", label: "path" },
                ]}
              />
            </div>
          </>
        )}
        {value.type === "postgres" && (
          <div style={{ gridColumn: "1 / -1" }}>
            <div style={labelStyle}>connection_string</div>
            <Input
              value={value.connection_string ?? ""}
              onChange={(e) => setField("connection_string", e.target.value)}
              placeholder="postgresql://user:pw@host:5432/db"
            />
          </div>
        )}
        {/* state/store have no kwargs */}
      </div>
    </div>
  );
}

export default function BackendBuilder({
  value,
  onChange,
}: BackendBuilderProps) {
  const isComposite = value && (value as CompositeSpec).type === "composite";
  const [mode, setMode] = useState<"independent" | "composite">(
    isComposite ? "composite" : "independent",
  );
  const [independent, setIndependent] = useState<IndependentSpec>(() =>
    !value || isComposite ? defaultIndependent() : (value as IndependentSpec),
  );
  const [composite, setComposite] = useState<CompositeSpec>(() =>
    isComposite ? (value as CompositeSpec) : defaultComposite(),
  );

  // Convert composite.routes (a Record) into an editable list to make
  // ordered insertions/removals trivial.
  const [routeList, setRouteList] = useState<RouteEntry[]>(() =>
    Object.entries(composite.routes).map(([prefix, spec]) => ({
      prefix,
      spec,
    })),
  );

  // Push effective spec upstream whenever any input changes.
  const effective: BackendSpec = useMemo(() => {
    if (mode === "independent") return independent;
    const routes: Record<string, IndependentSpec> = {};
    for (const r of routeList) {
      if (r.prefix.trim()) routes[r.prefix.trim()] = r.spec;
    }
    return { type: "composite", default: composite.default, routes };
  }, [mode, independent, composite, routeList]);

  useEffect(() => {
    onChange?.(effective);
  }, [effective, onChange]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <Form.Item
        label={
          <Space size={6}>
            <span>Backend</span>
            <Tooltip title="决定 agent 的工具/文件读写后端。Composite 模式按路径前缀路由到不同后端。">
              <Info size={12} color="var(--fn-text-tertiary)" />
            </Tooltip>
          </Space>
        }
        style={{ marginBottom: 0 }}
      >
        <Select
          value={mode}
          onChange={(v) => setMode(v as "independent" | "composite")}
          style={{ width: 220 }}
          options={[
            { value: "independent", label: "独立 backend(单一类型)" },
            { value: "composite", label: "Composite(按路径路由)" },
          ]}
        />
      </Form.Item>

      {mode === "independent" ? (
        <div
          style={{
            border: "1px solid var(--fn-border-secondary)",
            borderRadius: 6,
            padding: 12,
            background: "var(--fn-bg-secondary)",
          }}
        >
          <IndependentEditor
            value={independent}
            onChange={setIndependent}
            compact
          />
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div
            style={{
              border: "1px solid var(--fn-border-secondary)",
              borderRadius: 6,
              padding: 12,
              background: "var(--fn-bg-secondary)",
            }}
          >
            <Text strong style={{ fontSize: 13 }}>
              Default backend
            </Text>
            <Text
              style={{
                fontSize: 12,
                color: "var(--fn-text-tertiary)",
                marginLeft: 8,
              }}
            >
              所有未匹配 routes 前缀的请求落到这里
            </Text>
            <div style={{ marginTop: 8 }}>
              <IndependentEditor
                value={composite.default}
                onChange={(d) => setComposite({ ...composite, default: d })}
                compact
              />
            </div>
          </div>

          {routeList.map((entry, idx) => (
            <div
              key={idx}
              style={{
                border: "1px solid var(--fn-border-secondary)",
                borderRadius: 6,
                padding: 12,
                background: "var(--fn-bg-secondary)",
                position: "relative",
              }}
            >
              <Space style={{ position: "absolute", top: 8, right: 8 }}>
                <Tag color="blue">Route #{idx + 1}</Tag>
                <Button
                  size="small"
                  type="text"
                  danger
                  icon={<Trash2 size={12} />}
                  onClick={() =>
                    setRouteList((rs) => rs.filter((_, i) => i !== idx))
                  }
                />
              </Space>
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 12, color: "var(--fn-text-tertiary)" }}>
                  Path prefix
                </div>
                <Input
                  value={entry.prefix}
                  onChange={(e) =>
                    setRouteList((rs) =>
                      rs.map((r, i) =>
                        i === idx ? { ...r, prefix: e.target.value } : r,
                      ),
                    )
                  }
                  placeholder="/data"
                />
              </div>
              <IndependentEditor
                value={entry.spec}
                onChange={(s) =>
                  setRouteList((rs) =>
                    rs.map((r, i) => (i === idx ? { ...r, spec: s } : r)),
                  )
                }
                compact
              />
            </div>
          ))}

          <Button
            block
            icon={<Plus size={14} />}
            onClick={() =>
              setRouteList((rs) => [
                ...rs,
                { prefix: "", spec: defaultIndependent() },
              ])
            }
          >
            添加路由
          </Button>
        </div>
      )}

      {/* JSON preview */}
      <div>
        <div
          style={{
            fontSize: 12,
            color: "var(--fn-text-tertiary)",
            marginBottom: 4,
          }}
        >
          JSON preview
        </div>
        <pre
          style={{
            background: "var(--fn-bg-tertiary)",
            padding: 8,
            borderRadius: 6,
            fontSize: 11,
            margin: 0,
            maxHeight: 180,
            overflow: "auto",
          }}
        >
          {JSON.stringify(effective, null, 2)}
        </pre>
      </div>
    </div>
  );
}
