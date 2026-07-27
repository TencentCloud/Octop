import { useCallback, useState } from "react";
import { message, Modal } from "antd";
import { useTranslation } from "react-i18next";
import { request } from "../../../api/request";
import { useAsyncResource } from "../../../hooks/useAsyncResource";
import { showApiError } from "../../../utils/showApiToast";

/**
 * SkillSpec mirrors the JSON shape returned by octop's
 * ``GET /api/agents/{aid}/skills`` (see ``octop/api/routers/skills.py``).
 *
 * Field-name reconciliation: finnie's UI treats the identifier as ``slug``
 * and uses ``kind`` (``builtin`` | ``workspace``) to split built-in vs
 * customised skills. Octop only returns ``name`` and has no kind concept.
 *
 * To reuse finnie-style components without renaming everything, this
 * hook exposes ``slug`` (= server's ``name``) and synthesises ``kind``
 * (always ``"workspace"`` for now — every octop skill is editable).
 * The optional ``emoji`` from frontmatter is also surfaced for the card.
 */
export interface SkillSpec {
  /** Identifier used in URLs / list keys. Equal to the server's ``name``. */
  slug: string;
  /** Human readable name (server falls back to slug). */
  name: string;
  description: string;
  enabled: boolean;
  /** "workspace" for octop (no built-in registry). Kept for finnie parity. */
  kind: "workspace" | "builtin";
  emoji?: string;
  /** Persisted SkillHub marketplace icon. */
  iconUrl?: string;
}

export interface SkillDetail extends SkillSpec {
  /** Parsed YAML frontmatter (key/value, untyped). */
  frontmatter: Record<string, unknown>;
  /** Markdown body without the frontmatter block. */
  body: string;
  /** Raw SKILL.md content including frontmatter. */
  raw: string;
}

interface ServerSummary {
  /** Directory name — the stable identifier for operations. */
  slug?: string;
  /** Frontmatter display name (may differ from slug). */
  name: string;
  description: string;
  enabled: boolean;
  kind?: "workspace" | "builtin";
  emoji?: string;
  icon_url?: string;
}

interface ServerDetail extends ServerSummary {
  frontmatter: Record<string, unknown>;
  body: string;
  raw: string;
}

const toSpec = (row: ServerSummary): SkillSpec => ({
  // Prefer the directory-name slug for operations; fall back to name for
  // older backends that didn't return slug.
  slug: row.slug ?? row.name,
  name: row.name,
  description: row.description || "",
  enabled: row.enabled,
  kind: row.kind === "builtin" ? "builtin" : "workspace",
  emoji: row.emoji,
  iconUrl: row.icon_url,
});

const toDetail = (row: ServerDetail): SkillDetail => ({
  ...toSpec(row),
  frontmatter: row.frontmatter || {},
  body: row.body || "",
  raw: row.raw || "",
});

/**
 * Manage the per-agent skills list for the current ``activeAgentId``.
 */
export function useSkills(
  agentId: string | null,
  options?: { enabled?: boolean },
) {
  const { t } = useTranslation();
  const enabled = options?.enabled !== false && !!agentId;

  const {
    data: skills,
    loading,
    refresh: fetchSkills,
    setData: setSkills,
  } = useAsyncResource<SkillSpec[]>(
    [],
    async () => {
      const rows = await request<ServerSummary[]>(`/agents/${agentId}/skills`, {
        cache: "no-store",
      });
      return (rows || []).map(toSpec);
    },
    [agentId],
    {
      enabled,
      errorFallback: t("skills.loadFailed"),
      t,
      logLabel: "Skills",
    },
  );

  const getDetail = useCallback(
    async (slug: string): Promise<SkillDetail | null> => {
      if (!agentId) return null;
      try {
        const row = await request<ServerDetail>(
          `/agents/${agentId}/skills/${slug}`,
          { cache: "no-store" },
        );
        return toDetail(row);
      } catch (error) {
        console.error("Failed to load skill detail", error);
        showApiError(error, t("skills.loadDetailFailed"), t);
        return null;
      }
    },
    [agentId, t],
  );

  const createSkill = useCallback(
    async (name: string, content: string): Promise<boolean> => {
      if (!agentId) return false;
      try {
        await request(`/agents/${agentId}/skills`, {
          method: "POST",
          body: JSON.stringify({ name, content }),
        });
        message.success(t("skills.createSuccess"));
        await fetchSkills();
        return true;
      } catch (error) {
        console.error("Failed to save skill", error);
        showApiError(error, t("skills.createFailed"), t);
        return false;
      }
    },
    [agentId, fetchSkills, t],
  );

  const toggleEnabled = useCallback(
    async (skill: SkillSpec): Promise<boolean> => {
      if (!agentId) return false;
      const action = skill.enabled ? "disable" : "enable";
      try {
        await request(`/agents/${agentId}/skills/${skill.slug}/${action}`, {
          method: "POST",
          cache: "no-store",
        });
        setSkills((prev) =>
          prev.map((s) =>
            s.slug === skill.slug ? { ...s, enabled: !skill.enabled } : s,
          ),
        );
        message.success(
          skill.enabled
            ? t("skills.disabledSuccess")
            : t("skills.enabledSuccess"),
        );
        return true;
      } catch (error) {
        console.error("Failed to toggle skill", error);
        showApiError(error, t("skills.operationFailed"), t);
        return false;
      }
    },
    [agentId, setSkills, t],
  );

  const deleteSkill = useCallback(
    async (skill: SkillSpec): Promise<boolean> => {
      if (!agentId) return false;
      const confirmed = await new Promise<boolean>((resolve) => {
        Modal.confirm({
          title: t("common.delete"),
          content: t("skills.deleteConfirmContent", { slug: skill.slug }),
          okText: t("common.delete"),
          okType: "danger",
          cancelText: t("common.cancel"),
          onOk: () => resolve(true),
          onCancel: () => resolve(false),
        });
      });
      if (!confirmed) return false;

      try {
        await request(`/agents/${agentId}/skills/${skill.slug}`, {
          method: "DELETE",
        });
        message.success(t("skills.deleteSuccess"));
        await fetchSkills();
        return true;
      } catch (error) {
        console.error("Failed to delete skill", error);
        showApiError(error, t("skills.deleteFailed"), t);
        return false;
      }
    },
    [agentId, fetchSkills, t],
  );

  const [importing, setImporting] = useState(false);

  const importFromUrl = useCallback(
    async (bundleUrl: string): Promise<boolean> => {
      if (!agentId) return false;
      const trimmed = bundleUrl.trim();
      if (!trimmed) return false;
      try {
        setImporting(true);
        await request(`/agents/${agentId}/skills/import`, {
          method: "POST",
          body: JSON.stringify({ bundle_url: trimmed, enable: true }),
        });
        message.success(t("skills.importSuccess"));
        await fetchSkills();
        return true;
      } catch (error) {
        console.error("Failed to import skill from URL", error);
        showApiError(error, t("skills.importFailed"), t);
        return false;
      } finally {
        setImporting(false);
      }
    },
    [agentId, fetchSkills, t],
  );

  return {
    skills,
    loading,
    fetchSkills,
    getDetail,
    createSkill,
    importFromUrl,
    importing,
    toggleEnabled,
    deleteSkill,
  };
}
