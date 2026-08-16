import { request } from "../request";

export interface HitlPolicy {
  enabled: boolean;
  tools: string[] | "default";
  allowed_decisions: string[];
}

export interface FilesystemRule {
  operations: string[];
  paths: string[];
  mode: "allow" | "deny";
}

export interface FilesystemPolicy {
  enabled: boolean;
  rules: FilesystemRule[];
}

export interface PiiPolicy {
  enabled: boolean;
  strategy: "block" | "redact" | "mask" | "hash";
  surfaces: string[];
}

export interface SkillScanPolicy {
  mode: "off" | "warn" | "block";
}

export interface ToolGuardPolicy {
  enabled: boolean;
  mode: "block" | "warn" | "require_approval";
}

export interface ToolGuardRule {
  id: string;
  tools: string[];
  params: string[];
  category: string;
  severity: string;
  description: string;
  remediation: string;
  patterns: string[];
  exclude_patterns: string[];
}

export interface ToolGuardRulesResponse {
  rules: ToolGuardRule[];
  path: string;
  rule_count: number;
}

export interface ToolGuardRulesRawResponse {
  path: string;
  content: string;
}

export interface ToolGuardRulesSaveResponse {
  path: string;
  rule_count: number;
}

export interface HitlToolCatalogItem {
  name: string;
  label_zh: string;
  label_en: string;
}

export interface SecurityDefaults {
  hitl_tools: string[];
  hitl_tool_catalog: HitlToolCatalogItem[];
  tool_guard_rules: ToolGuardRule[];
}

export interface SecurityPolicy {
  hitl: HitlPolicy;
  filesystem: FilesystemPolicy;
  pii: PiiPolicy;
  skill_scan: SkillScanPolicy;
  tool_guard: ToolGuardPolicy;
}

export const securityApi = {
  getPolicy(): Promise<SecurityPolicy> {
    return request<SecurityPolicy>("/admin/security");
  },
  savePolicy(body: Partial<SecurityPolicy>): Promise<SecurityPolicy> {
    return request<SecurityPolicy>("/admin/security", {
      method: "PUT",
      body: JSON.stringify(body),
    });
  },
  getToolGuardRules(): Promise<ToolGuardRulesResponse> {
    return request<ToolGuardRulesResponse>("/admin/security/tool-guard/rules");
  },
  getToolGuardRulesRaw(): Promise<ToolGuardRulesRawResponse> {
    return request<ToolGuardRulesRawResponse>(
      "/admin/security/tool-guard/rules/raw",
    );
  },
  saveToolGuardRulesRaw(content: string): Promise<ToolGuardRulesSaveResponse> {
    return request<ToolGuardRulesSaveResponse>(
      "/admin/security/tool-guard/rules/raw",
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    );
  },
  resetToolGuardRules(): Promise<ToolGuardRulesRawResponse> {
    return request<ToolGuardRulesRawResponse>(
      "/admin/security/tool-guard/rules/reset",
      {
        method: "POST",
      },
    );
  },
  getDefaults(): Promise<SecurityDefaults> {
    return request<SecurityDefaults>("/admin/security/defaults");
  },
};
