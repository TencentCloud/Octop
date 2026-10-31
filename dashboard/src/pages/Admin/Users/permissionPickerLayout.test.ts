import { describe, expect, it } from "vitest";
import { buildPermissionPickerGroups } from "./permissionPickerLayout";

const CATALOG = [
  "experts",
  "tasks",
  "token_usage",
  "skills",
  "skill_builtin",
  "skill_market",
  "subagents",
  "tools",
  "agent_plugins",
  "mbti",
  "memory",
  "channels",
  "connector_enabled",
  "connector_builtin",
  "connector_custom",
  "skill_packages",
  "knowledge_bases",
  "bridge",
  "terminal",
  "browser",
  "desktop",
  "mobile",
  "users",
  "user_roles",
  "user_groups",
  "sso_feishu",
  "sso_wecom",
  "sso_dingtalk",
  "sso_oidc",
  "sso_ldap",
  "sso_external",
  "providers",
  "ollama_models",
  "onnx_models",
  "model_generation",
  "model_decision",
  "storage_backends",
  "plugins",
  "plugin_market",
  "security_hitl",
  "security_filesystem",
  "security_pii",
  "security_tool_guard",
  "security_skill_scan",
  "admin_console",
  "envs",
  "search",
  "knowledge_settings",
  "voice",
  "observability",
  "backup",
  "tls",
  "update",
  "captcha",
].map((key) => ({ key, label: key }));

function summarize(
  layout: Parameters<typeof buildPermissionPickerGroups>[1],
  catalog: { key: string; label: string }[] = CATALOG,
) {
  return buildPermissionPickerGroups(catalog, layout, (key) => key).map(
    (group) => ({
      id: group.id,
      label: group.label,
      blocks: group.blocks.map((block) => {
        if (block.kind === "page") {
          return {
            kind: block.kind,
            id: block.id,
            title: block.title,
            keys: block.items.map((item) => item.key),
          };
        }
        const keys = block.items.map((item) =>
          item.kind === "always" ? item.key : item.item.key,
        );
        const fixed = block.items.flatMap((item) =>
          item.kind === "always" ? [item.key] : [],
        );
        return fixed.length > 0
          ? { kind: block.kind, keys, fixed }
          : { kind: block.kind, keys };
      }),
    }),
  );
}

describe("buildPermissionPickerGroups", () => {
  it("follows the default sidebar groups and nests tab permissions", () => {
    expect(summarize(null)).toEqual([
      {
        id: "ungrouped",
        label: "nav.ungrouped",
        blocks: [
          {
            kind: "chips",
            keys: ["chat", "experts", "tasks", "token_usage"],
            fixed: ["chat"],
          },
        ],
      },
      {
        id: "settings",
        label: "nav.settings",
        blocks: [
          {
            kind: "chips",
            keys: [
              "skills",
              "skill_builtin",
              "skill_market",
              "subagents",
              "tools",
              "agent_plugins",
              "mbti",
              "memory",
              "channels",
            ],
          },
          {
            kind: "page",
            id: "connectors",
            title: "nav.connectors",
            keys: [
              "connector_enabled",
              "connector_builtin",
              "connector_custom",
            ],
          },
          {
            kind: "chips",
            keys: ["skill_packages"],
          },
          {
            kind: "page",
            id: "knowledge-bases",
            title: "nav.knowledgeBases",
            keys: ["knowledge_bases", "knowledge_settings"],
          },
          {
            kind: "chips",
            keys: ["bridge"],
          },
        ],
      },
      {
        id: "control",
        label: "nav.control",
        blocks: [
          {
            kind: "page",
            id: "workbench",
            title: "nav.workbench",
            keys: ["terminal", "browser"],
          },
          {
            kind: "page",
            id: "remote-desktop",
            title: "nav.remoteDesktop",
            keys: ["desktop", "mobile"],
          },
        ],
      },
      {
        id: "admin",
        label: "nav.admin",
        blocks: [
          {
            kind: "page",
            id: "admin-users",
            title: "nav.adminUsers",
            keys: [
              "users",
              "user_roles",
              "user_groups",
              "sso_feishu",
              "sso_wecom",
              "sso_dingtalk",
              "sso_oidc",
              "sso_ldap",
              "sso_external",
            ],
          },
          {
            kind: "page",
            id: "models",
            title: "nav.models",
            keys: [
              "providers",
              "ollama_models",
              "onnx_models",
              "model_generation",
              "voice",
              "model_decision",
              "search",
            ],
          },
          { kind: "chips", keys: ["storage_backends"] },
          {
            kind: "page",
            id: "admin-plugins",
            title: "nav.adminPlugins",
            keys: ["plugins", "plugin_market"],
          },
          {
            kind: "page",
            id: "admin-security",
            title: "nav.security",
            keys: [
              "security_hitl",
              "security_filesystem",
              "security_pii",
              "security_tool_guard",
              "security_skill_scan",
              "admin_console",
            ],
          },
          {
            kind: "page",
            id: "admin-advanced",
            title: "nav.adminAdvanced",
            keys: [
              "envs",
              "observability",
              "backup",
              "tls",
              "captcha",
              "update",
            ],
          },
        ],
      },
    ]);
  });

  it("uses the operator layout, and keeps hidden items in the default group", () => {
    const groups = summarize({
      groups: [
        { id: "c_abcdef01", name: "常用" },
        { id: "admin", name: "系统" },
        { id: "settings" },
        { id: "control" },
      ],
      items: [
        { key: "channels", group: "c_abcdef01" },
        { key: "models", group: "admin" },
        { key: "admin-users", group: "admin" },
        { key: "workbench", hidden: true },
        { key: "chat" },
      ],
    });
    expect(groups.map((group) => [group.id, group.label])).toEqual([
      ["ungrouped", "nav.ungrouped"],
      ["c_abcdef01", "常用"],
      ["admin", "系统"],
      ["settings", "nav.settings"],
      ["control", "nav.control"],
    ]);
    expect(groups[0]?.blocks).toEqual([
      {
        kind: "chips",
        keys: ["chat", "experts", "tasks", "token_usage"],
        fixed: ["chat"],
      },
    ]);
    expect(groups[1]?.blocks).toEqual([{ kind: "chips", keys: ["channels"] }]);
    expect(groups[2]?.blocks.map((block) => block.keys[0])).toEqual([
      "providers",
      "users",
      "storage_backends",
      "plugins",
      "security_hitl",
      "envs",
    ]);
    expect(groups[3]?.blocks[0]).toMatchObject({
      kind: "chips",
      keys: [
        "skills",
        "skill_builtin",
        "skill_market",
        "subagents",
        "tools",
        "agent_plugins",
        "mbti",
        "memory",
      ],
    });
    expect(
      groups[4]?.blocks.map((block) => ("id" in block ? block.id : "")),
    ).toEqual(["workbench", "remote-desktop"]);
  });

  it("keeps personalization tabs with channels in the user's nav group", () => {
    const groups = summarize({
      groups: [
        { id: "c_abcdef01", name: "常用" },
        { id: "settings", name: "配置" },
      ],
      items: [
        { key: "personalization", group: "c_abcdef01" },
        { key: "channels", group: "c_abcdef01" },
        { key: "connectors", group: "settings" },
      ],
    });
    expect(groups.find((group) => group.id === "other")).toBeUndefined();
    expect(groups.find((group) => group.id === "c_abcdef01")?.blocks).toEqual([
      {
        kind: "chips",
        keys: [
          "skills",
          "skill_builtin",
          "skill_market",
          "subagents",
          "tools",
          "agent_plugins",
          "mbti",
          "memory",
          "channels",
        ],
      },
    ]);
    expect(
      groups
        .find((group) => group.id === "settings")
        ?.blocks.some(
          (block) =>
            block.kind === "page" && block.keys.includes("connector_enabled"),
        ),
    ).toBe(true);
  });

  it("puts an unmapped permission in Other", () => {
    const groups = summarize(null, [
      ...CATALOG,
      { key: "future_perm", label: "Future" },
    ]);
    expect(groups.at(-1)).toMatchObject({
      id: "other",
      label: "adminUsers.permGroupOther",
      blocks: [{ kind: "chips", keys: ["future_perm"] }],
    });
  });
});
