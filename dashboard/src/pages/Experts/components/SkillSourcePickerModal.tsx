import { useEffect, useMemo, useState } from "react";
import { Button, Drawer, Empty, Input, List, Segmented, Spin } from "antd";
import { useTranslation } from "react-i18next";

import { request } from "../../../api/request";
import { useAgent } from "../../../context/AgentContext";
import { ownedSoloExperts } from "../../../utils/sharedExpert";
import { apiErrorMessage } from "../../../utils/apiError";
import { message } from "@/utils/antdMessage";
import SkillHubTab, {
  hubInstallPresentation,
} from "../../Agent/Skills/components/SkillHubTab";
import type { SkillHubSkill } from "../../Agent/Skills/components/SkillHubDetailDrawer";
import { parseSkillPreviewFromMarkdown } from "../../Agent/Skills/skillMarkdown";
import styles from "../index.module.less";

export interface PickedHubSkill {
  skill_name: string;
  display_name: string;
  icon_url: string;
  label?: { zh?: string; en?: string };
  summary?: { zh?: string; en?: string };
}

export interface PickedAgentSkill {
  agent_id: string;
  slug: string;
  name: string;
  description: string;
  content: string;
}

type PickerTab = "hub" | "agents";

interface SkillSummary {
  slug?: string;
  name: string;
  description?: string;
  kind?: "builtin" | "workspace" | "package";
}

interface SkillSourcePickerModalProps {
  open: boolean;
  excludeSlugs: ReadonlySet<string>;
  excludeAgentId?: string;
  loadContent?: boolean;
  onClose: () => void;
  onPickHub: (skill: PickedHubSkill) => void;
  onPickAgentSkill: (skill: PickedAgentSkill) => void;
}

export default function SkillSourcePickerModal({
  open,
  excludeSlugs,
  excludeAgentId,
  loadContent = true,
  onClose,
  onPickHub,
  onPickAgentSkill,
}: SkillSourcePickerModalProps) {
  const { t } = useTranslation();
  const { agents } = useAgent();
  const [tab, setTab] = useState<PickerTab>("hub");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillSummary[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [copyingSlug, setCopyingSlug] = useState<string | null>(null);

  const selectableAgents = useMemo(
    () =>
      ownedSoloExperts(agents).filter(
        (agent) => agent.agent_id !== excludeAgentId,
      ),
    [agents, excludeAgentId],
  );

  useEffect(() => {
    if (!open) {
      setTab("hub");
      setSelectedAgentId(null);
      setSkills([]);
      setQuery("");
    }
  }, [open]);

  useEffect(() => {
    if (!open || !selectedAgentId) {
      setSkills([]);
      return;
    }
    let cancelled = false;
    setSkillsLoading(true);
    request<SkillSummary[]>(`/agents/${selectedAgentId}/skills`)
      .then((rows) => {
        if (!cancelled) {
          setSkills((rows ?? []).filter((row) => row.kind !== "builtin"));
        }
      })
      .catch(() => {
        if (!cancelled) setSkills([]);
      })
      .finally(() => {
        if (!cancelled) setSkillsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, selectedAgentId]);

  const filteredSkills = useMemo(() => {
    const q = query.trim().toLowerCase();
    return skills.filter((skill) => {
      const slug = skill.slug ?? skill.name;
      if (excludeSlugs.has(slug)) return false;
      if (!q) return true;
      return (
        slug.toLowerCase().includes(q) ||
        skill.name.toLowerCase().includes(q) ||
        (skill.description || "").toLowerCase().includes(q)
      );
    });
  }, [excludeSlugs, query, skills]);

  const handlePickHub = (skill: SkillHubSkill) => {
    if (excludeSlugs.has(skill.slug)) return;
    const presentation = hubInstallPresentation(skill);
    onPickHub({
      skill_name: skill.slug,
      display_name: skill.name,
      icon_url: skill.iconUrl ?? "",
      label: presentation.label,
      summary: presentation.summary,
    });
    onClose();
  };

  const handleCopySkill = async (skill: SkillSummary) => {
    if (!selectedAgentId) return;
    const slug = skill.slug ?? skill.name;
    setCopyingSlug(slug);
    try {
      if (!loadContent) {
        onPickAgentSkill({
          agent_id: selectedAgentId,
          slug,
          name: skill.name,
          description: skill.description || "",
          content: "",
        });
        onClose();
        return;
      }
      const detail = await request<{ raw?: string }>(
        `/agents/${selectedAgentId}/skills/${encodeURIComponent(slug)}`,
      );
      const content = detail.raw ?? "";
      const preview = parseSkillPreviewFromMarkdown(content, slug);
      onPickAgentSkill({
        agent_id: selectedAgentId,
        slug,
        name: preview.name || skill.name,
        description: preview.description || skill.description || "",
        content,
      });
      onClose();
    } catch (err) {
      message.error(apiErrorMessage(err, t("experts.copySkillFailed"), t));
    } finally {
      setCopyingSlug(null);
    }
  };

  return (
    <Drawer
      open={open}
      title={t("experts.addSkillTitle")}
      width={720}
      onClose={onClose}
      destroyOnHidden
    >
      <Segmented
        block
        value={tab}
        onChange={(value) => setTab(value === "agents" ? "agents" : "hub")}
        options={[
          { label: t("experts.addSkillFromHub"), value: "hub" },
          { label: t("experts.addSkillFromAgent"), value: "agents" },
        ]}
        style={{ marginBottom: 16 }}
      />
      {tab === "hub" ? (
        <SkillHubTab
          target={{ type: "browse" }}
          onPick={handlePickHub}
          pickedSlugs={excludeSlugs}
        />
      ) : selectedAgentId ? (
        <>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: 8,
              marginBottom: 12,
            }}
          >
            <Button
              type="link"
              style={{ padding: 0 }}
              onClick={() => setSelectedAgentId(null)}
            >
              {t("experts.backToAgents")}
            </Button>
            <Input
              allowClear
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("experts.searchAgentSkills")}
              style={{ maxWidth: 240 }}
            />
          </div>
          {skillsLoading ? (
            <div style={{ textAlign: "center", padding: 32 }}>
              <Spin />
            </div>
          ) : filteredSkills.length === 0 ? (
            <Empty description={t("experts.noAgentSkills")} />
          ) : (
            <List
              dataSource={filteredSkills}
              renderItem={(skill) => {
                const slug = skill.slug ?? skill.name;
                return (
                  <List.Item
                    key={slug}
                    actions={[
                      <Button
                        key="pick"
                        type="link"
                        loading={copyingSlug === slug}
                        onClick={() => void handleCopySkill(skill)}
                      >
                        {t("experts.pickSkill")}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={skill.name || slug}
                      description={skill.description || slug}
                    />
                  </List.Item>
                );
              }}
            />
          )}
        </>
      ) : selectableAgents.length === 0 ? (
        <Empty description={t("experts.noOtherAgents")} />
      ) : (
        <div className={styles.fileList}>
          {selectableAgents.map((agent) => (
            <button
              key={agent.agent_id}
              type="button"
              className={styles.fileItemMain}
              style={{ width: "100%", marginBottom: 8 }}
              onClick={() => setSelectedAgentId(agent.agent_id)}
            >
              <div className={styles.fileMeta}>
                <div className={styles.fileLabel}>{agent.name}</div>
                <div className={styles.filePath}>
                  {agent.description || agent.agent_id}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </Drawer>
  );
}
