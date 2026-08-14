import { useState, useEffect, useCallback, useImperativeHandle, forwardRef } from "react";
import { useTranslation } from "react-i18next";
import { Button, Input } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { agentChatApi } from "@/api/modules/agentChat";
import type { LocalizedText } from "@/utils/localizedText";
import { iconForName } from "./iconForName";
import { pastelIconBackground } from "@/utils/pastelIconBackground";
import styles from "../index.module.less";

export interface QuickPrompt {
  title: LocalizedText;
  description: LocalizedText;
  prompt: LocalizedText;
  color: string;
  icon_name: string | null;
}

export interface WelcomeConfigData {
  welcome_message?: LocalizedText;
  quick_prompts: QuickPrompt[];
}

interface WelcomeConfigProps {
  agentId: string;
}


const defaultQuickPrompt: QuickPrompt = {
  title: { zh: "", en: "" },
  description: { zh: "", en: "" },
  prompt: { zh: "", en: "" },
  color: "#e8f4ff",
  icon_name: null,
};

const presetColors = [
  "#e8f4ff",
  "#eef2ff",
  "#f0fdf4",
  "#fff7ed",
  "#fef3c7",
  "#fdf2f8",
  "#faf5ff",
];

// 图标名必须来自 iconForName 的 iconMap，否则会全部回退成默认图标造成重复。
// 以下 16 个名字在 iconMap 中均存在且互不相同。
const presetIcons = [
  "file-text",
  "message-square",
  "globe",
  "sparkles",
  "pen-tool",
  "book-open",
  "zap",
  "bar-chart-3",
  "list-todo",
  "mail",
  "hard-drive",
  "palette",
  "activity",
  "video",
  "terminal",
  "wrench",
];

export interface WelcomeConfigRef {
  getData: () => WelcomeConfigData;
}

const WelcomeConfig = forwardRef<WelcomeConfigRef, WelcomeConfigProps>(
  ({ agentId }, ref) => {
    const { t, i18n } = useTranslation();
    const [loading, setLoading] = useState(false);
    const [welcomeMessage, setWelcomeMessage] = useState("");
    const [quickPrompts, setQuickPrompts] = useState<QuickPrompt[]>([]);

    useImperativeHandle(ref, () => ({
      getData: () => ({
        welcome_message: welcomeMessage ? {
          zh: welcomeMessage,
          en: welcomeMessage,
        } : undefined,
        quick_prompts: quickPrompts,
      }),
    }));

    const loadConfig = useCallback(async () => {
      setLoading(true);
      try {
        const data = await agentChatApi.welcome(agentId);
        const currentLang = i18n.language.startsWith("zh") ? "zh" : "en";
        const wm = data.welcome_message;
        const msg = wm ? (wm[currentLang] || wm.zh || wm.en || "") : "";
        setWelcomeMessage(msg || "");
        setQuickPrompts(
          (data.quick_prompts || []).map((p) => ({
            title: {
              zh: p.title?.zh ?? "",
              en: p.title?.en ?? "",
            },
            description: {
              zh: p.description?.zh ?? "",
              en: p.description?.en ?? "",
            },
            prompt: {
              zh: p.prompt?.zh ?? "",
              en: p.prompt?.en ?? "",
            },
            color: p.color || "#e8f4ff",
            icon_name: p.icon_name ?? null,
          }))
        );
      } catch {
        setWelcomeMessage("");
        setQuickPrompts([]);
      } finally {
        setLoading(false);
      }
    }, [agentId, i18n.language]);

    useEffect(() => {
      loadConfig();
    }, [loadConfig]);

    const addQuickPrompt = () => {
      setQuickPrompts([...quickPrompts, { ...defaultQuickPrompt }]);
    };

    const removeQuickPrompt = (index: number) => {
      setQuickPrompts(quickPrompts.filter((_, i) => i !== index));
    };

    const updateQuickPrompt = (
      index: number,
      field: keyof QuickPrompt,
      value: any
    ) => {
      const newPrompts = [...quickPrompts];
      newPrompts[index] = { ...newPrompts[index], [field]: value };
      setQuickPrompts(newPrompts);
    };

    const updateLocalizedField = (
      index: number,
      field: "title" | "description" | "prompt",
      lang: "zh" | "en",
      value: string
    ) => {
      const newPrompts = [...quickPrompts];
      const currentField = newPrompts[index][field];
      newPrompts[index] = {
        ...newPrompts[index],
        [field]: {
          zh: currentField?.zh ?? "",
          en: currentField?.en ?? "",
          [lang]: value,
        },
      };
      setQuickPrompts(newPrompts);
    };

    const currentLang = i18n.language.startsWith("zh") ? "zh" : "en";

    return (
      <div className={styles.welcomeConfig}>
        {loading ? (
          <div className={styles.welcomeConfigLoading}>{t("common.loading")}</div>
        ) : (
          <>
            <div className={styles.welcomeConfigSection}>
              <h4>{t("experts.welcomeMessageTitle")}</h4>
              <div className={styles.welcomeMessageField}>
                <Input.TextArea
                  value={welcomeMessage}
                  onChange={(e) => setWelcomeMessage(e.target.value)}
                  placeholder={t("experts.welcomeMessagePlaceholder")}
                  rows={2}
                />
              </div>
            </div>

            <div className={styles.welcomeConfigSection}>
              <div className={styles.quickPromptsHeader}>
                <h4>{t("experts.quickPromptsTitle")}</h4>
                <Button type="dashed" icon={<PlusOutlined />} onClick={addQuickPrompt}>
                  {t("experts.addQuickPrompt")}
                </Button>
              </div>

              <div className={styles.quickPromptsList}>
                {quickPrompts.map((prompt, index) => (
                  <div key={index} className={styles.quickPromptItem}>
                    <div className={styles.quickPromptHeader}>
                      <span className={styles.quickPromptIndex}>{index + 1}</span>
                      <Button
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => removeQuickPrompt(index)}
                      />
                    </div>

                    <div className={styles.quickPromptFields}>
                      <div className={styles.quickPromptRow}>
                        <div className={styles.quickPromptField}>
                          <label>{t("experts.quickPromptTitle")}</label>
                          <Input
                            value={prompt.title[currentLang]}
                            onChange={(e) =>
                              updateLocalizedField(index, "title", currentLang, e.target.value)
                            }
                            placeholder={t("experts.quickPromptTitlePlaceholder")}
                          />
                        </div>
                        <div className={styles.quickPromptField}>
                          <label>{t("experts.quickPromptDescription")}</label>
                          <Input
                            value={prompt.description[currentLang]}
                            onChange={(e) =>
                              updateLocalizedField(
                                index,
                                "description",
                                currentLang,
                                e.target.value
                              )
                            }
                            placeholder={t("experts.quickPromptDescriptionPlaceholder")}
                          />
                        </div>
                      </div>

                      <div className={styles.quickPromptRow}>
                        <div className={styles.quickPromptFieldFull}>
                          <label>{t("experts.quickPromptContent")}</label>
                          <Input.TextArea
                            value={prompt.prompt[currentLang]}
                            onChange={(e) =>
                              updateLocalizedField(index, "prompt", currentLang, e.target.value)
                            }
                            placeholder={t("experts.quickPromptContentPlaceholder")}
                            rows={2}
                          />
                        </div>
                      </div>

                      <div className={styles.quickPromptRow}>
                        <div className={styles.quickPromptField}>
                          <label>{t("experts.quickPromptColor")}</label>
                          <div className={styles.colorPicker}>
                            {presetColors.map((color) => (
                              <button
                                key={color}
                                type="button"
                                className={
                                  styles.colorOption +
                                  (prompt.color === color ? " " + styles.colorOptionActive : "")
                                }
                                style={{ backgroundColor: color }}
                                onClick={() => updateQuickPrompt(index, "color", color)}
                              />
                            ))}
                          </div>
                        </div>
                        <div className={styles.quickPromptField}>
                          <label>{t("experts.quickPromptIcon")}</label>
                          <div className={styles.iconPicker}>
                            <button
                              type="button"
                              className={
                                styles.iconOption +
                                " " +
                                styles.iconOptionNoIcon +
                                (!prompt.icon_name ? " " + styles.iconOptionActive : "")
                              }
                              onClick={() => updateQuickPrompt(index, "icon_name", null)}
                            >
                              {t("experts.noIcon")}
                            </button>
                            {presetIcons.map((icon) => (
                              <button
                                key={icon}
                                type="button"
                                className={
                                  styles.iconOption +
                                  (prompt.icon_name === icon ? " " + styles.iconOptionActive : "")
                                }
                                onClick={() => updateQuickPrompt(index, "icon_name", icon)}
                              >
                                {iconForName(icon, 16)}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {quickPrompts.length > 0 && (
                        <div className={styles.quickPromptPreview}>
                          <div className={styles.quickPromptPreviewLabel}>
                            {t("experts.quickPromptPreview")}
                          </div>
                          <div className={styles.quickCardPreview}>
                            <div
                              className={styles.quickCardIcon}
                              style={{
                                background: pastelIconBackground(prompt.color, index),
                                color: "rgba(15,23,42,0.55)",
                              }}
                            >
                              {iconForName(prompt.icon_name, 18)}
                            </div>
                            <div className={styles.quickCardBody}>
                              <span className={styles.quickCardTitle}>
                                {prompt.title[currentLang] ||
                                  t("experts.quickPromptTitlePlaceholder")}
                              </span>
                              <span className={styles.quickCardDesc}>
                                {prompt.description[currentLang] ||
                                  t("experts.quickPromptDescriptionPlaceholder")}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {quickPrompts.length === 0 && (
                  <div className={styles.quickPromptsEmpty}>
                    {t("experts.noQuickPrompts")}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    );
  }
);

WelcomeConfig.displayName = "WelcomeConfig";
export default WelcomeConfig;
