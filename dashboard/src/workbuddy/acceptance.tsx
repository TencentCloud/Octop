import UnifiedMarketHeader from "./UnifiedMarketHeader";
import { MARKET_TABS } from "./marketModel";
/** Development-only fixtures render production components with fixed data and local callbacks. */
import { createRoot } from "react-dom/client";
import { useEffect, useRef, useState } from "react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import i18next from "i18next";
import { initReactI18next, useTranslation } from "react-i18next";
import { Button, ConfigProvider, Drawer, Modal, theme } from "antd";
import { Moon, Sun, Settings } from "lucide-react";
import zh from "../locales/zh.json";
import en from "../locales/en.json";
import WorkBuddyNavigation from "./Navigation";
import SidebarFrame from "./SidebarFrame";
import ShellFrame from "./ShellFrame";
import Topbar from "./Topbar";
import ConversationLayout from "./ConversationLayout";
import ChatInput, {
  type ChatInputHandle,
} from "../pages/Chat/components/ChatInput";
import { AntdAppProvider } from "../components/AntdAppProvider";
import { useIsMobile } from "../hooks/useIsMobile";
import { buildNavSections } from "../layouts/sidebarNav";
import {
  workBuddyBrandTokens,
  workBuddySurfaceTokens,
  workBuddyDarkComponents,
} from "./theme";
import { WorkBuddyHistoryList } from "../pages/Chat/components/SessionList";
import chatStyles from "../pages/Chat/index.module.less";
import expertStyles from "../pages/Experts/index.module.less";
import "../styles/layout.css";
import "../styles/form-override.css";
import "./acceptanceServices";
import { DEFERRED_FEATURES, type DeferredFeatureId } from "./capabilities";
import Welcome from "./Welcome";
import SettingsFrame from "./SettingsFrame";
import AutomationList from "./AutomationList";
import ConnectorTile from "./ConnectorTile";
import SkillTile from "./SkillTile";
import UserMessageSurface from "./UserMessageSurface";
import HitlApprovalCard from "../pages/Chat/components/HitlApprovalCard";
import AskQuestionCard from "../pages/Chat/components/AskQuestionCard";
import PlanReadyCard from "../pages/Chat/components/PlanReadyCard";
import type { CronJobSpecOutput } from "../api/types";
import DeferredFeature from "../pages/DeferredFeature";
import { ExpertCard } from "../pages/Experts/components/ExpertCard";
import "../styles/theme-vars.css";
import "./styles.css";
import "./round3.css";
import "./acceptance.css";

if (!import.meta.env.DEV)
  throw new Error("UI acceptance fixtures are development-only");

function Acceptance() {
  const { t, i18n } = useTranslation();
  const [dark, setDark] = useState(false);
  const [page, setPage] = useState("home");
  const [feature, setFeature] = useState<DeferredFeatureId>("projects");
  const [settings, setSettings] = useState(false);
  const composer = useRef<ChatInputHandle>(null);
  const isMobile = useIsMobile();
  const [collapsed, setCollapsed] = useState(isMobile);
  useEffect(() => {
    const toggle = () => setCollapsed((value) => !value);
    window.addEventListener("octop:toggle-nav", toggle);
    return () => window.removeEventListener("octop:toggle-nav", toggle);
  }, []);
  const navigate = useNavigate();
  const [selection, setSelection] = useState("");
  const lang = i18n.language.startsWith("zh") ? "zh" : "en";
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);
  const toggleTheme = () => {
    document.documentElement.dataset.theme = dark ? "light" : "dark";
    setDark(!dark);
  };
  const marketPage = ["experts", "skills", "connectors"].includes(page);
  const settingsContent = (
    <SettingsFrame user={null}>
      <section data-settings-group="account">
        <p>开发样例：真实账户表单由 Octop 登录后的界面提供。</p>
      </section>
      <section data-settings-group="appearance">
        <Button onClick={toggleTheme}>
          {dark ? "Light theme" : "Dark theme"}
        </Button>
      </section>
    </SettingsFrame>
  );
  return (
    <ConfigProvider
      prefixCls="octop"
      theme={{
        algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          ...workBuddyBrandTokens(dark),
          ...workBuddySurfaceTokens(dark, isMobile),
        },
        components: dark ? workBuddyDarkComponents() : {},
      }}
    >
      <AntdAppProvider>
        <div className="wb-acceptance-banner">
          <span>开发验收样例 · 不连接业务接口 · 非原版运行截图</span>
          <div className="wb-acceptance-actions">
            <button
              type="button"
              onClick={() =>
                void i18n.changeLanguage(lang === "zh" ? "en" : "zh")
              }
            >
              {lang === "zh" ? "English" : "中文"}
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={dark ? "Light theme" : "Dark theme"}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              type="button"
              onClick={() => {
                navigate("/settings/account");
                setSettings(true);
              }}
              aria-label="Settings"
            >
              <Settings size={18} />
            </button>
          </div>
        </div>
        <ShellFrame style={{ height: "calc(100dvh - 28px)" }}>
          <SidebarFrame
            collapsed={collapsed}
            onToggle={() => setCollapsed(!collapsed)}
            isMobile={isMobile}
            navigation={
              <WorkBuddyNavigation
                compact={collapsed && !isMobile}
                sections={buildNavSections({
                  id: 0,
                  username: "visual-fixture",
                  display_name: "Visual fixture",
                  role: "user",
                  locale: lang,
                  permissions: ["connectors", "skills"],
                })}
                onNavigate={(path) => {
                  navigate(path);
                  const pages: Record<string, string> = {
                    "/home": "home",
                    "/chat": "messages",
                    "/experts": "experts",
                    "/tasks": "automation",
                    "/connectors": "connectors",
                    "/skills": "skills",
                  };
                  setPage(pages[path] ?? "deferred");
                  const selected = DEFERRED_FEATURES.find(
                    (item) => item.path === path,
                  );
                  if (selected) setFeature(selected.id);
                  if (isMobile) setCollapsed(true);
                }}
              />
            }
            history={
              <WorkBuddyHistoryList
                sessions={[
                  {
                    id: "fixture-thread",
                    threadId: "fixture-thread",
                    name: "开发验收会话",
                    channelType: "ui",
                    updatedAt: null,
                  },
                ]}
                activeId={null}
                activeAgentId="fixture-agent"
                hasMore={false}
                loadingMore={false}
                onLoadMore={() => {}}
                onFetchAllSessions={() => {}}
                onSelect={() => {
                  setPage("messages");
                  navigate("/chat");
                }}
                onDelete={() => setSelection("删除展示样例：没有删除")}
                onRename={() => setSelection("重命名展示样例：没有保存")}
                onPin={() => setSelection("置顶展示样例：没有保存")}
                onFork={() => setSelection("分叉展示样例：没有创建会话")}
              />
            }
            footer={
              <button
                type="button"
                onClick={() => {
                  navigate("/settings/account");
                  setSettings(true);
                }}
              >
                {t("account.settings")}
              </button>
            }
          />
          <main
            className={marketPage ? "wb-unified-market" : "wb-acceptance-main"}
          >
            <Topbar
              title={
                marketPage ? (
                  <UnifiedMarketHeader
                    tabs={MARKET_TABS}
                    active={page}
                    onSelect={(tab) => {
                      navigate(tab.path);
                      setPage(tab.id);
                    }}
                  />
                ) : (
                  "Octop"
                )
              }
            />
            {page === "home" ? (
              <div
                className={`${chatStyles.chatPage} wb-chat wb-chat--welcome`}
              >
                <div className={`${chatStyles.chatMain} wb-chat-main`}>
                  <ConversationLayout
                    welcome
                    cards={[
                      {
                        title: t("chatWelcome.newChat"),
                        description: t("chatWelcome.inputPlaceholder"),
                        prompt: t("chatWelcome.inputPlaceholder"),
                        color: "",
                      },
                      {
                        title: t("nav.experts"),
                        description: t("chatWelcome.inputPlaceholder"),
                        prompt: t("chatWelcome.inputPlaceholder"),
                        color: "",
                      },
                    ]}
                    onPromptClick={(text) =>
                      composer.current?.setPrefillText(text)
                    }
                  >
                    <div
                      className={`${chatStyles.chatContent} wb-chat-content`}
                    >
                      <Welcome
                        quickCards={[]}
                        onPromptClick={(text) =>
                          composer.current?.setPrefillText(text)
                        }
                      />
                    </div>
                    <ChatInput
                      ref={composer}
                      isStreaming={false}
                      onSend={() =>
                        setSelection("输入状态样例：没有创建会话或发起执行")
                      }
                      onCancel={() => {}}
                      onNewChat={() => composer.current?.setPrefillText("")}
                    />
                  </ConversationLayout>
                </div>
              </div>
            ) : page === "experts" ? (
              <div className="wb-market-pane">
                <div className={`${expertStyles.cardGrid} wb-expert-grid`}>
                  {["research", "writing", "coding"].map((id) => (
                    <ExpertCard
                      key={id}
                      expert={{
                        id,
                        label: { zh: `${id} 专家`, en: `${id} expert` },
                        description: {
                          zh: "开发验收中的模板展示样例",
                          en: "Template display fixture for UI acceptance",
                        },
                      }}
                      lang={lang}
                      isInstalled={false}
                      onCreate={(expert) => setSelection(expert.id)}
                    />
                  ))}
                </div>
                {selection && <p role="status">样例选择：{selection}</p>}
              </div>
            ) : page === "skills" ? (
              <div className="wb-market-pane">
                <div className="wb-skill-hub-grid">
                  {["工作纪要", "文档整理", "只读技能包"].map((name, index) => (
                    <SkillTile
                      key={name}
                      title={name}
                      description="原版技能卡片展示样例；不安装、不启用、不删除任何技能"
                      icon={name.charAt(0)}
                      enabled={index !== 1}
                      sourceLabel={index === 2 ? "package" : undefined}
                      onOpen={() => setSelection(`详情样例：${name}`)}
                      actions={
                        index === 2 ? undefined : (
                          <button
                            className="skill-add-btn"
                            type="button"
                            aria-label="Skill action sample"
                            onClick={() =>
                              setSelection(`操作样例：${name}（没有保存）`)
                            }
                          >
                            +
                          </button>
                        )
                      }
                    />
                  ))}
                </div>
                {selection && <p role="status">{selection}</p>}
              </div>
            ) : page === "messages" ? (
              <div className="wb-acceptance-market">
                <h2>{t("nav.chat")}</h2>
                <div className="wb-acceptance-user-message">
                  <UserMessageSurface>
                    <p>这是一条开发验收消息，仅检查原版用户气泡的排版。</p>
                    <p>
                      This message is a visual fixture. No conversation is
                      created or sent.
                    </p>
                  </UserMessageSurface>
                </div>
                <HitlApprovalCard
                  actions={[
                    {
                      name: "write_file",
                      args: { path: "notes.md", content: "fixture" },
                    },
                  ]}
                  status="pending"
                  onDecision={() =>
                    setSelection("Approval fixture: no execution")
                  }
                />
                <AskQuestionCard
                  questions={[
                    {
                      question: "Choose the fixture task",
                      header: "Fixture",
                      options: [
                        { label: "Research", description: "Fixed data" },
                        { label: "Writing", description: "Fixed data" },
                      ],
                      multi_select: false,
                    },
                  ]}
                  status="pending"
                  onSubmit={() =>
                    setSelection(
                      "Question fixture: no business response submitted",
                    )
                  }
                />
                <PlanReadyCard
                  path="plans/fixture.md"
                  onExecute={() => setSelection("Plan fixture: no execution")}
                  onKeepEditing={() => setSelection("Plan fixture: no save")}
                />
                {selection && <p role="status">{selection}</p>}
              </div>
            ) : page === "connectors" ? (
              <div className="wb-market-pane">
                <div className="connector-grid">
                  {["配置样例", "共享只读样例", "未接入样例"].map(
                    (name, index) => (
                      <ConnectorTile
                        key={name}
                        name={name}
                        description="仅用于验证连接器卡片结构，不连接任何服务"
                        icon={name.charAt(0)}
                        installed={index === 1}
                        disabled={index === 2}
                        status={
                          index === 2 ? (
                            <span className="connector-card-badge">
                              {t("workbuddy.notConnected")}
                            </span>
                          ) : undefined
                        }
                        onOpen={
                          index === 0
                            ? () => setSelection("配置样例，没有保存或连接")
                            : undefined
                        }
                        actions={
                          index === 0 ? (
                            <button
                              type="button"
                              className="connector-connect-btn"
                              aria-label="Configuration sample"
                              onClick={() =>
                                setSelection("配置样例，没有保存或连接")
                              }
                            >
                              +
                            </button>
                          ) : null
                        }
                      />
                    ),
                  )}
                </div>
                {selection && <p role="status">{selection}</p>}
              </div>
            ) : page === "automation" ? (
              <div className="wb-acceptance-market">
                <h2>{t("nav.tasks")}</h2>
                <AutomationList
                  jobs={
                    [
                      {
                        id: "fixture-daily",
                        name: "每日工作汇总",
                        enabled: true,
                        schedule: {
                          type: "cron",
                          cron: "0 9 * * *",
                          timezone: "Asia/Shanghai",
                        },
                        task_type: "text",
                        text: "开发样例，无业务请求",
                      },
                      {
                        id: "fixture-weekly",
                        name: "每周资料整理",
                        enabled: false,
                        schedule: {
                          type: "cron",
                          cron: "0 9 * * 1",
                          timezone: "Asia/Shanghai",
                        },
                        task_type: "text",
                        text: "开发样例，无业务请求",
                      },
                    ] as CronJobSpecOutput[]
                  }
                  timeZone="Asia/Shanghai"
                  disabled={false}
                  onDetail={(job) => setSelection(`详情样例：${job.id}`)}
                  onEdit={(job) => setSelection(`编辑样例：${job.id}`)}
                  onExecuteNow={(job) =>
                    setSelection(`执行按钮样例：${job.id}（没有发起执行）`)
                  }
                  onToggleEnabled={(job) =>
                    setSelection(`启停按钮样例：${job.id}（没有保存）`)
                  }
                  onDelete={(id) =>
                    setSelection(`删除按钮样例：${id}（没有删除）`)
                  }
                />
                {selection && <p role="status">{selection}</p>}
              </div>
            ) : (
              <DeferredFeature feature={feature} />
            )}
          </main>
        </ShellFrame>
        {selection && page === "home" && (
          <p className="wb-acceptance-status" role="status">
            {selection}
          </p>
        )}
        {isMobile ? (
          <Drawer
            title={t("workbuddy.settings.title")}
            open={settings}
            onClose={() => setSettings(false)}
            placement="bottom"
            height="100dvh"
            destroyOnHidden
            className="wb-settings-drawer"
            styles={{ body: { padding: 0 } }}
          >
            {settingsContent}
          </Drawer>
        ) : (
          <Modal
            open={settings}
            onCancel={() => setSettings(false)}
            footer={null}
            destroyOnHidden
            centered
            width={880}
            className="wb-settings-modal"
          >
            {settingsContent}
          </Modal>
        )}
      </AntdAppProvider>
    </ConfigProvider>
  );
}

void i18next
  .use(initReactI18next)
  .init({
    lng: "zh",
    fallbackLng: "en",
    resources: { zh: { translation: zh }, en: { translation: en } },
    interpolation: { escapeValue: false },
  })
  .then(() =>
    createRoot(document.getElementById("root")!).render(
      <MemoryRouter initialEntries={["/home"]}>
        <Acceptance />
      </MemoryRouter>,
    ),
  );
