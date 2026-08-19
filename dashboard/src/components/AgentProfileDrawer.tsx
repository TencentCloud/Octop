import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Collapse, Drawer, Spin, Tag } from "antd";
import { ChevronLeft, FolderOpen } from "lucide-react";
import { request } from "../api/request";
import { withFromWorkspace } from "../utils/fromWorkspace";
import type { OctopAgent } from "../context/AgentContext";
import { isAgentChatReady } from "../utils/agentError";
import {
  listAgentSubagents,
  type AgentSubagentSummary,
} from "../api/modules/subagents";
import MbtiPersonaTag from "./MbtiPersonaTag";
import { metaForFile } from "../pages/Experts/components/iconForName";
import { fetchConfigMdFiles } from "../pages/Experts/components/expertFileGroups";
import { useSkillDisplayName } from "../pages/Agent/Skills/skillDisplayNames";
import SubagentCatalogDrawer from "../pages/Experts/components/SubagentCatalogDrawer";
import SkillCatalogDrawer from "../pages/Experts/components/SkillCatalogDrawer";
import WorkspaceDrawer from "../pages/Agent/Workspace/components/WorkspaceDrawer";
import expertStyles from "../pages/Experts/index.module.less";
import styles from "./AgentProfileDrawer.module.less";

interface AgentDetail {
  name: string;
  description: string | null;
}

interface SkillSummary {
  slug?: string;
  name: string;
  description?: string;
  enabled?: boolean;
  kind?: "builtin" | "workspace";
}

function workspaceSkills(skills: SkillSummary[]): SkillSummary[] {
  return skills.filter((s) => s.kind !== "builtin");
}

interface AgentProfileDrawerProps {
  open: boolean;
  agent: OctopAgent | null;
  isMobile?: boolean;
  onClose: () => void;
}

export default function AgentProfileDrawer({
  open,
  agent,
  isMobile = false,
  onClose,
}: AgentProfileDrawerProps) {
  const { t } = useTranslation();
  const skillDisplayName = useSkillDisplayName();
  const [loading, setLoading] = useState(false);
  const [filesLoading, setFilesLoading] = useState(false);
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);
  const [agentSkills, setAgentSkills] = useState<SkillSummary[]>([]);
  const [subagents, setSubagents] = useState<AgentSubagentSummary[]>([]);
  const [viewingFile, setViewingFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [fileLoading, setFileLoading] = useState(false);
  const [skillCatalogOpen, setSkillCatalogOpen] = useState(false);
  const [subagentCatalogOpen, setSubagentCatalogOpen] = useState(false);
  const [workspaceDrawerOpen, setWorkspaceDrawerOpen] = useState(false);

  const installedSlugs = useMemo(
    () => new Set(subagents.map((s) => s.slug)),
    [subagents],
  );

  const reloadSubagents = useCallback(async () => {
    if (!agent) return;
    try {
      const rows = await listAgentSubagents(agent.agent_id);
      setSubagents(rows);
    } catch {
      /* non-critical */
    }
  }, [agent]);

  useEffect(() => {
    if (!open || !agent) return;
    let cancelled = false;
    setLoading(true);
    setDetail(null);
    setWorkspaceFiles([]);
    setAgentSkills([]);
    setSubagents([]);
    setViewingFile(null);
    setFileContent("");

    const load = async () => {
      try {
        const ag = await request<AgentDetail>(`/agents/${agent.agent_id}`);
        if (cancelled) return;
        setDetail(ag);
        setLoading(false);

        if (isAgentChatReady(agent.state)) {
          setFilesLoading(true);
          void fetchConfigMdFiles(agent.agent_id)
            .then((files) => {
              if (!cancelled) setWorkspaceFiles(files);
            })
            .catch(() => {
              if (!cancelled) setWorkspaceFiles([]);
            })
            .finally(() => {
              if (!cancelled) setFilesLoading(false);
            });

          void request<SkillSummary[]>(`/agents/${agent.agent_id}/skills`)
            .then((skills) => {
              if (!cancelled) setAgentSkills(workspaceSkills(skills));
            })
            .catch(() => {
              if (!cancelled) setAgentSkills([]);
            });

          void listAgentSubagents(agent.agent_id)
            .then((rows) => {
              if (!cancelled) setSubagents(rows);
            })
            .catch(() => {
              if (!cancelled) setSubagents([]);
            });
        }
      } catch {
        if (!cancelled) setLoading(false);
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [open, agent]);

  useEffect(() => {
    if (!open) {
      setViewingFile(null);
      setFileContent("");
      setSkillCatalogOpen(false);
      setSubagentCatalogOpen(false);
      setWorkspaceDrawerOpen(false);
    }
  }, [open]);

  const openFileView = async (filePath: string) => {
    if (!agent) return;
    const path = filePath.startsWith("/") ? filePath : `/${filePath}`;
    setViewingFile(path);
    setFileLoading(true);
    setFileContent("");
    try {
      const r = await request<{ content: string }>(
        withFromWorkspace(
          `/agents/${agent.agent_id}/workspace/file?path=${encodeURIComponent(
            path,
          )}`,
        ),
      );
      setFileContent(r.content ?? "");
    } catch {
      setFileContent("");
    } finally {
      setFileLoading(false);
    }
  };

  const closeFileView = () => {
    setViewingFile(null);
    setFileContent("");
  };

  const handleDrawerClose = () => {
    if (isMobile && viewingFile) {
      closeFileView();
      return;
    }
    onClose();
  };

  const displayName = (path: string) => path.replace(/^\//, "");

  const mobileDrawerStyles = {
    body: {
      padding: "12px 16px calc(16px + env(safe-area-inset-bottom))",
    },
  };

  const renderFileContent = () =>
    fileLoading ? (
      <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
        <Spin />
      </div>
    ) : (
      <pre className={styles.fileContent}>
        {fileContent || t("workspace.emptyFile")}
      </pre>
    );

  const renderProfileContent = () => {
    if (loading) {
      return (
        <div style={{ display: "flex", justifyContent: "center", padding: 40 }}>
          <Spin />
        </div>
      );
    }

    if (!agent) {
      return null;
    }

    return (
      <>
        <div className={expertStyles.drawerSection}>
          <div className={expertStyles.drawerSectionTitle}>
            {t("experts.basicInfo")}
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
            {detail?.name ?? agent.name}
          </div>
          <p
            style={{
              margin: 0,
              fontSize: 13,
              lineHeight: 1.6,
              color: "var(--fn-text-secondary)",
              wordBreak: "break-word",
            }}
          >
            {detail?.description ||
              agent.description ||
              t("chat.agentNoDescription")}
          </p>
          <div
            style={{
              marginTop: 10,
              display: "flex",
              alignItems: "center",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <span style={{ fontSize: 12, color: "var(--fn-text-tertiary)" }}>
              {t("experts.table.persona")}
            </span>
            <MbtiPersonaTag value={agent.persona_mbti} />
          </div>
          <button
            type="button"
            className={styles.workspaceOpenBtn}
            disabled={!isAgentChatReady(agent.state)}
            title={
              isAgentChatReady(agent.state)
                ? undefined
                : t("workspace.requiresRunning")
            }
            onClick={() => {
              if (!isAgentChatReady(agent.state)) return;
              setWorkspaceDrawerOpen(true);
            }}
          >
            <FolderOpen size={14} strokeWidth={2} />
            {t("chat.openWorkspace", "工作区")}
          </button>
        </div>

        <div className={expertStyles.drawerSection}>
          <Collapse
            ghost
            className={expertStyles.drawerCollapse}
            defaultActiveKey={["config"]}
            items={[
              {
                key: "config",
                label: (
                  <div className={styles.sectionTitleRow}>
                    <div className={expertStyles.drawerSectionTitle}>
                      {t("experts.configFiles", {
                        count: workspaceFiles.length,
                      })}
                    </div>
                    <button
                      type="button"
                      className={styles.viewMoreLink}
                      disabled={!isAgentChatReady(agent.state)}
                      title={
                        isAgentChatReady(agent.state)
                          ? undefined
                          : t("workspace.requiresRunning")
                      }
                      onClick={(event) => {
                        event.stopPropagation();
                        if (!isAgentChatReady(agent.state)) return;
                        setWorkspaceDrawerOpen(true);
                      }}
                    >
                      {t("common.viewMore")}
                    </button>
                  </div>
                ),
                children: (
                  <div className={expertStyles.fileList}>
                    {filesLoading ? (
                      <div
                        style={{
                          display: "flex",
                          justifyContent: "center",
                          padding: "16px 0",
                        }}
                      >
                        <Spin size="small" />
                      </div>
                    ) : workspaceFiles.length === 0 ? (
                      <div
                        style={{
                          fontSize: 13,
                          color: "var(--fn-text-tertiary)",
                          padding: "8px 0",
                        }}
                      >
                        {t("experts.noWorkspaceFiles")}
                      </div>
                    ) : (
                      workspaceFiles.map((file) => {
                        const basename = displayName(file);
                        const meta = metaForFile(basename, t);
                        return (
                          <div key={file} className={expertStyles.fileItem}>
                            <button
                              type="button"
                              className={expertStyles.fileItemMain}
                              onClick={() => void openFileView(file)}
                            >
                              <div
                                className={expertStyles.fileIcon}
                                style={{
                                  color: meta.color,
                                  background: `${meta.color}1a`,
                                }}
                              >
                                {meta.icon}
                              </div>
                              <div className={expertStyles.fileMeta}>
                                <div className={expertStyles.fileLabel}>
                                  {meta.label}
                                </div>
                                <div className={expertStyles.filePath}>
                                  {basename}
                                </div>
                              </div>
                              <span className={expertStyles.fileHint}>
                                {t("common.view")}
                              </span>
                            </button>
                          </div>
                        );
                      })
                    )}
                  </div>
                ),
              },
            ]}
          />
        </div>

        <div className={expertStyles.drawerSection}>
          <Collapse
            ghost
            className={expertStyles.drawerCollapse}
            defaultActiveKey={["skills"]}
            items={[
              {
                key: "skills",
                label: (
                  <div className={styles.sectionTitleRow}>
                    <div className={expertStyles.drawerSectionTitle}>
                      {t("experts.skillFilesTitle", {
                        count: agentSkills.length,
                      })}
                    </div>
                    <button
                      type="button"
                      className={styles.viewMoreLink}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSkillCatalogOpen(true);
                      }}
                    >
                      {t("common.viewMore")}
                    </button>
                  </div>
                ),
                children: (
                  <>
                    <p
                      style={{
                        fontSize: 12,
                        color: "var(--fn-text-tertiary)",
                        margin: "0 0 8px",
                      }}
                    >
                      {t("experts.skillFilesHint")}
                    </p>
                    <div className={expertStyles.fileList}>
                      {agentSkills.length === 0 ? (
                        <div
                          style={{
                            fontSize: 13,
                            color: "var(--fn-text-tertiary)",
                            padding: "8px 0",
                          }}
                        >
                          {t("experts.noSkillFiles")}
                        </div>
                      ) : (
                        agentSkills.map((skill) => (
                          <div
                            key={skill.slug ?? skill.name}
                            className={expertStyles.fileItem}
                          >
                            <div className={styles.skillItemRow}>
                              <div className={expertStyles.fileMeta}>
                                <div className={expertStyles.fileLabel}>
                                  {skillDisplayName(skill)}
                                </div>
                                {skill.description ? (
                                  <div className={expertStyles.filePath}>
                                    {skill.description}
                                  </div>
                                ) : null}
                              </div>
                              <span className={expertStyles.fileHint}>
                                {skill.enabled === false
                                  ? t("common.disabled")
                                  : t("common.enabled")}
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </>
                ),
              },
            ]}
          />
        </div>

        <div className={expertStyles.drawerSection}>
          <Collapse
            ghost
            className={expertStyles.drawerCollapse}
            defaultActiveKey={["subagents"]}
            items={[
              {
                key: "subagents",
                label: (
                  <div className={styles.sectionTitleRow}>
                    <div className={expertStyles.drawerSectionTitle}>
                      {t("experts.subagentFilesTitle", {
                        count: subagents.length,
                      })}
                    </div>
                    <button
                      type="button"
                      className={styles.viewMoreLink}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSubagentCatalogOpen(true);
                      }}
                    >
                      {t("common.viewMore")}
                    </button>
                  </div>
                ),
                children: (
                  <>
                    <p
                      style={{
                        fontSize: 12,
                        color: "var(--fn-text-tertiary)",
                        margin: "0 0 8px",
                      }}
                    >
                      {t("experts.subagentFilesHint")}
                    </p>
                    <div className={expertStyles.fileList}>
                      {subagents.length === 0 ? (
                        <div
                          style={{
                            fontSize: 13,
                            color: "var(--fn-text-tertiary)",
                            padding: "8px 0",
                          }}
                        >
                          {t("experts.noSubagentFiles")}
                        </div>
                      ) : (
                        subagents.map((sub) => (
                          <div key={sub.slug} className={expertStyles.fileItem}>
                            <div className={styles.skillItemRow}>
                              <div className={expertStyles.fileMeta}>
                                <div className={expertStyles.fileLabel}>
                                  {sub.emoji ? (
                                    <span style={{ marginRight: 6 }}>
                                      {sub.emoji}
                                    </span>
                                  ) : null}
                                  {sub.name}
                                </div>
                                {sub.description ? (
                                  <div className={expertStyles.filePath}>
                                    {sub.description}
                                  </div>
                                ) : null}
                              </div>
                              <Tag
                                color="blue"
                                style={{
                                  margin: 0,
                                  fontSize: 11,
                                  lineHeight: "18px",
                                }}
                              >
                                {sub.slug}
                              </Tag>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </>
                ),
              },
            ]}
          />
        </div>
      </>
    );
  };

  const mobileTitle =
    viewingFile !== null ? (
      <button
        type="button"
        className={styles.drawerTitleBack}
        onClick={closeFileView}
      >
        <ChevronLeft size={18} strokeWidth={2} />
        <span>{displayName(viewingFile)}</span>
      </button>
    ) : (
      t("chat.agentProfile.title")
    );

  if (isMobile) {
    return (
      <>
        <Drawer
          open={open}
          title={mobileTitle}
          width="100%"
          placement="bottom"
          height="82vh"
          rootClassName={styles.mobileDrawer}
          styles={mobileDrawerStyles}
          onClose={handleDrawerClose}
          destroyOnHidden
        >
          {viewingFile ? renderFileContent() : renderProfileContent()}
        </Drawer>

        <SkillCatalogDrawer
          agentId={agent?.agent_id ?? ""}
          open={skillCatalogOpen}
          onClose={() => setSkillCatalogOpen(false)}
        />
        <SubagentCatalogDrawer
          agentId={agent?.agent_id ?? ""}
          agentState={agent?.state ?? "stopped"}
          open={subagentCatalogOpen}
          installedSlugs={installedSlugs}
          onClose={() => setSubagentCatalogOpen(false)}
          onInstalled={() => void reloadSubagents()}
        />
        <WorkspaceDrawer
          agentId={agent?.agent_id ?? ""}
          open={workspaceDrawerOpen}
          onClose={() => setWorkspaceDrawerOpen(false)}
        />
      </>
    );
  }

  return (
    <>
      <Drawer
        open={open}
        title={t("chat.agentProfile.title")}
        width={420}
        onClose={onClose}
        destroyOnHidden
      >
        {renderProfileContent()}
      </Drawer>

      <Drawer
        open={viewingFile !== null}
        title={viewingFile ? displayName(viewingFile) : ""}
        width={480}
        onClose={closeFileView}
        destroyOnHidden
      >
        {renderFileContent()}
      </Drawer>

      <SkillCatalogDrawer
        agentId={agent?.agent_id ?? ""}
        open={skillCatalogOpen}
        onClose={() => setSkillCatalogOpen(false)}
      />
      <SubagentCatalogDrawer
        agentId={agent?.agent_id ?? ""}
        agentState={agent?.state ?? "stopped"}
        open={subagentCatalogOpen}
        installedSlugs={installedSlugs}
        onClose={() => setSubagentCatalogOpen(false)}
        onInstalled={() => void reloadSubagents()}
      />
      <WorkspaceDrawer
        agentId={agent?.agent_id ?? ""}
        open={workspaceDrawerOpen}
        onClose={() => setWorkspaceDrawerOpen(false)}
      />
    </>
  );
}
