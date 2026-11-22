import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { Alert, Button, Form, Input, Typography, type InputRef } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Check, ChevronDown } from "lucide-react";
import { agentChatApi } from "@/api/modules/agentChat";
import { pickLocale } from "@/utils/localizedText";
import { pastelIconBackground } from "@/utils/pastelIconBackground";
import { iconForName } from "./iconForName";
import ExpertConfigDrawer from "./expertDrawer/ExpertConfigDrawer";
import ExpertTextAssistField from "./expertDrawer/ExpertTextAssistField";
import styles from "../index.module.less";
import {
  filterQuickPrompts,
  normalizeQuickPrompts,
  type QuickPrompt,
  type WelcomeManifestSnapshot,
  type WelcomeManifestStatus,
} from "./welcomeManifest";

interface WelcomeConfigProps {
  agentId?: string;
  initialPrompts?: QuickPrompt[];
  templateStatus?: WelcomeManifestStatus;
  showPrompts?: boolean;
  disabled?: boolean;
  editing?: boolean;
  kind?: "expert.welcome_message" | "team.welcome_message";
  value?: string;
  onChange?: (value: string) => void;
}

export interface WelcomeConfigRef {
  getSnapshot: () => WelcomeManifestSnapshot;
}

interface WelcomeDraft {
  welcome_message?: string;
}

const emptyPrompts: QuickPrompt[] = [];

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

interface WelcomeEditorProps {
  formId: string;
  value?: string;
  getName: () => string;
  editing: boolean;
  kind: NonNullable<WelcomeConfigProps["kind"]>;
  status: WelcomeManifestStatus;
  showPrompts: boolean;
  prompts: QuickPrompt[];
  onApply: (
    title: string | undefined,
    prompts: QuickPrompt[] | undefined,
  ) => void;
}

function WelcomeEditor({
  formId,
  value,
  getName,
  editing,
  kind,
  status,
  showPrompts,
  prompts,
  onApply,
}: WelcomeEditorProps) {
  const { t, i18n } = useTranslation();
  const [initialTitle] = useState(value);
  const [draftPrompts, setDraftPrompts] = useState<QuickPrompt[]>();
  const reduceMotion = useReducedMotion();
  const [expanded, setExpanded] = useState<number | null>(null);
  const quickPrompts = draftPrompts ?? prompts;
  const currentLang = i18n.language.startsWith("zh") ? "zh" : "en";
  const promptId = useId();
  const focusNewPrompt = useRef(false);
  const focusTitle = useCallback((input: InputRef | null) => {
    if (!input || !focusNewPrompt.current) return;
    focusNewPrompt.current = false;
    input.focus();
  }, []);

  const addQuickPrompt = () => {
    focusNewPrompt.current = true;
    setDraftPrompts([...quickPrompts, { ...defaultQuickPrompt }]);
    setExpanded(quickPrompts.length);
  };

  const removeQuickPrompt = (index: number) => {
    setDraftPrompts(quickPrompts.filter((_, i) => i !== index));
    if (expanded === index) setExpanded(null);
    else if (expanded !== null && expanded > index) setExpanded(expanded - 1);
  };

  const updateQuickPrompt = (index: number, patch: Partial<QuickPrompt>) => {
    setDraftPrompts(
      quickPrompts.map((prompt, i) =>
        i === index ? { ...prompt, ...patch } : prompt,
      ),
    );
  };

  const updateLocalizedField = (
    index: number,
    field: "title" | "description" | "prompt",
    value: string,
  ) => {
    updateQuickPrompt(index, {
      [field]: { ...quickPrompts[index][field], [currentLang]: value },
    });
  };

  return (
    <Form<WelcomeDraft>
      id={formId}
      name={formId}
      layout="vertical"
      initialValues={{ welcome_message: initialTitle }}
      onFinish={({ welcome_message }) =>
        onApply(
          welcome_message === initialTitle ? undefined : welcome_message ?? "",
          draftPrompts,
        )
      }
    >
      <ExpertTextAssistField
        name="welcome_message"
        label={t("experts.welcomeMessageTitle")}
        tooltip={t(
          editing ? "experts.editWelcomeHint" : "experts.createWelcomeHint",
        )}
        kind={kind}
        getName={getName}
      >
        <Input.TextArea
          autoSize={{ minRows: 3 }}
          placeholder={t("experts.welcomeMessagePlaceholder")}
        />
      </ExpertTextAssistField>
      {showPrompts && (
        <section className={styles.welcomeConfigSection}>
          <div className={styles.quickPromptsHeader}>
            <h4>{t("experts.quickPromptsTitle")}</h4>
            <Button
              icon={<PlusOutlined />}
              disabled={status !== "ready"}
              onClick={addQuickPrompt}
            >
              {t("experts.addQuickPrompt")}
            </Button>
          </div>
          {status === "loading" ? (
            <div className={styles.welcomeConfigLoading}>
              {t("common.loading")}
            </div>
          ) : status === "error" ? (
            <Alert
              type="warning"
              showIcon
              message={t("experts.quickPromptsLoadFailed")}
            />
          ) : quickPrompts.length === 0 ? (
            <div className={styles.quickPromptsEmpty}>
              {t("experts.noQuickPrompts")}
            </div>
          ) : (
            <div className={styles.quickPromptsList}>
              {quickPrompts.map((prompt, index) => {
                const isExpanded = expanded === index;
                const title =
                  pickLocale(prompt.title, currentLang).trim() ||
                  t("experts.untitledQuickPrompt");
                const description = pickLocale(
                  prompt.description,
                  currentLang,
                ).trim();
                const detailsId = `${promptId}-${index}`;
                return (
                  <div key={index} className={styles.quickPromptItem}>
                    <div className={styles.quickPromptHeader}>
                      <button
                        type="button"
                        className={styles.quickPromptToggle}
                        aria-expanded={isExpanded}
                        aria-controls={detailsId}
                        onClick={() => setExpanded(isExpanded ? null : index)}
                      >
                        <span
                          aria-hidden
                          className={styles.quickPromptBadge}
                          style={{
                            background: pastelIconBackground(
                              prompt.color,
                              index,
                            ),
                          }}
                        >
                          {iconForName(prompt.icon_name, 16)}
                        </span>
                        <span className={styles.quickPromptSummary}>
                          <Typography.Text ellipsis title={title}>
                            {title}
                          </Typography.Text>
                          {description && (
                            <span className={styles.quickPromptDescription}>
                              {description}
                            </span>
                          )}
                        </span>
                        <ChevronDown
                          size={14}
                          aria-hidden
                          className={styles.quickPromptChevron}
                        />
                      </button>
                      <Button
                        type="text"
                        className={styles.quickPromptDelete}
                        icon={<DeleteOutlined />}
                        aria-label={t("experts.deleteQuickPrompt", { title })}
                        onClick={() => removeQuickPrompt(index)}
                      />
                    </div>
                    <div
                      id={detailsId}
                      aria-hidden={!isExpanded}
                      ref={(panel) => {
                        panel?.toggleAttribute("inert", !isExpanded);
                      }}
                    >
                      <AnimatePresence initial={false}>
                        {isExpanded && (
                          <motion.div
                            key="editor"
                            className={styles.quickPromptPanel}
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: "auto", opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{
                              duration: reduceMotion ? 0 : 0.2,
                              ease: "easeOut",
                            }}
                          >
                            <div className={styles.quickPromptFields}>
                              <div className={styles.quickPromptRow}>
                                <div className={styles.quickPromptField}>
                                  <label htmlFor={`${detailsId}-title`}>
                                    {t("experts.quickPromptTitle")}
                                  </label>
                                  <Input
                                    id={`${detailsId}-title`}
                                    ref={focusTitle}
                                    value={prompt.title[currentLang]}
                                    onChange={(e) =>
                                      updateLocalizedField(
                                        index,
                                        "title",
                                        e.target.value,
                                      )
                                    }
                                    placeholder={t(
                                      "experts.quickPromptTitlePlaceholder",
                                    )}
                                  />
                                </div>
                                <div className={styles.quickPromptField}>
                                  <label htmlFor={`${detailsId}-description`}>
                                    {t("experts.quickPromptDescription")}
                                  </label>
                                  <Input
                                    id={`${detailsId}-description`}
                                    value={prompt.description[currentLang]}
                                    onChange={(e) =>
                                      updateLocalizedField(
                                        index,
                                        "description",
                                        e.target.value,
                                      )
                                    }
                                    placeholder={t(
                                      "experts.quickPromptDescriptionPlaceholder",
                                    )}
                                  />
                                </div>
                              </div>

                              <div className={styles.quickPromptRow}>
                                <div className={styles.quickPromptFieldFull}>
                                  <label htmlFor={`${detailsId}-content`}>
                                    {t("experts.quickPromptContent")}
                                  </label>
                                  <Input.TextArea
                                    id={`${detailsId}-content`}
                                    value={prompt.prompt[currentLang]}
                                    onChange={(e) =>
                                      updateLocalizedField(
                                        index,
                                        "prompt",
                                        e.target.value,
                                      )
                                    }
                                    placeholder={t(
                                      "experts.quickPromptContentPlaceholder",
                                    )}
                                    autoSize={{ minRows: 2 }}
                                  />
                                </div>
                              </div>

                              <div className={styles.quickPromptAppearance}>
                                <div className={styles.quickPromptField}>
                                  <label id={`${detailsId}-color`}>
                                    {t("experts.quickPromptColor")}
                                  </label>
                                  <div
                                    className={styles.colorPicker}
                                    role="group"
                                    aria-labelledby={`${detailsId}-color`}
                                  >
                                    {presetColors.map((color) => (
                                      <button
                                        key={color}
                                        aria-label={color}
                                        aria-pressed={prompt.color === color}
                                        type="button"
                                        className={
                                          styles.colorOption +
                                          (prompt.color === color
                                            ? " " + styles.colorOptionActive
                                            : "")
                                        }
                                        style={{ backgroundColor: color }}
                                        onClick={() =>
                                          updateQuickPrompt(index, { color })
                                        }
                                      >
                                        {prompt.color === color && (
                                          <Check size={15} aria-hidden />
                                        )}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                                <div className={styles.quickPromptField}>
                                  <label id={`${detailsId}-icon`}>
                                    {t("experts.quickPromptIcon")}
                                  </label>
                                  <div
                                    className={styles.iconPicker}
                                    role="group"
                                    aria-labelledby={`${detailsId}-icon`}
                                  >
                                    <button
                                      type="button"
                                      aria-pressed={!prompt.icon_name}
                                      aria-label={t(
                                        "experts.defaultQuickPromptIcon",
                                      )}
                                      title={t(
                                        "experts.defaultQuickPromptIcon",
                                      )}
                                      className={
                                        styles.iconOption +
                                        (!prompt.icon_name
                                          ? " " + styles.iconOptionActive
                                          : "")
                                      }
                                      onClick={() =>
                                        updateQuickPrompt(index, {
                                          icon_name: null,
                                        })
                                      }
                                    >
                                      {iconForName(null, 16)}
                                    </button>
                                    {presetIcons.map((icon) => (
                                      <button
                                        key={icon}
                                        aria-label={t(
                                          `experts.iconLabels.${icon}`,
                                          {
                                            defaultValue: icon,
                                          },
                                        )}
                                        aria-pressed={prompt.icon_name === icon}
                                        type="button"
                                        className={
                                          styles.iconOption +
                                          (prompt.icon_name === icon
                                            ? " " + styles.iconOptionActive
                                            : "")
                                        }
                                        onClick={() =>
                                          updateQuickPrompt(index, {
                                            icon_name: icon,
                                          })
                                        }
                                      >
                                        {iconForName(icon, 16)}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              </div>

                              <div className={styles.quickPromptPreview}>
                                <div className={styles.quickPromptPreviewLabel}>
                                  {t("experts.quickPromptPreview")}
                                </div>
                                <div className={styles.quickCardPreview}>
                                  <div
                                    className={styles.quickCardIcon}
                                    style={{
                                      background: pastelIconBackground(
                                        prompt.color,
                                        index,
                                      ),
                                      color: "rgba(15,23,42,0.55)",
                                    }}
                                  >
                                    {iconForName(prompt.icon_name, 18)}
                                  </div>
                                  <div className={styles.quickCardBody}>
                                    <span className={styles.quickCardTitle}>
                                      {prompt.title[currentLang] ||
                                        t(
                                          "experts.quickPromptTitlePlaceholder",
                                        )}
                                    </span>
                                    <span className={styles.quickCardDesc}>
                                      {prompt.description[currentLang] ||
                                        t(
                                          "experts.quickPromptDescriptionPlaceholder",
                                        )}
                                    </span>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}
    </Form>
  );
}

const WelcomeConfig = forwardRef<WelcomeConfigRef, WelcomeConfigProps>(
  (
    {
      agentId,
      initialPrompts,
      templateStatus = "ready",
      showPrompts = true,
      disabled = false,
      editing = false,
      kind = "expert.welcome_message",
      value,
      onChange,
    },
    ref,
  ) => {
    const { t } = useTranslation();
    const parentForm = Form.useFormInstance();
    const formId = useId();
    const [open, setOpen] = useState(false);
    const [loaded, setLoaded] = useState<{
      agentId: string;
      status: WelcomeManifestStatus;
      prompts: QuickPrompt[];
    }>();
    const [appliedPrompts, setAppliedPrompts] = useState<QuickPrompt[]>();
    const currentLoad = loaded?.agentId === agentId ? loaded : undefined;
    const status = agentId ? currentLoad?.status ?? "loading" : templateStatus;
    const prompts =
      appliedPrompts ??
      (agentId ? currentLoad?.prompts : initialPrompts) ??
      emptyPrompts;

    useEffect(() => {
      if (!agentId) return;
      let ignore = false;
      agentChatApi.welcome(agentId).then(
        (data) => {
          if (!ignore)
            setLoaded({
              agentId,
              status: "ready",
              prompts: normalizeQuickPrompts(data.quick_prompts),
            });
        },
        () => {
          if (!ignore) setLoaded({ agentId, status: "error", prompts: [] });
        },
      );
      return () => {
        ignore = true;
      };
    }, [agentId]);

    useImperativeHandle(
      ref,
      () => ({
        getSnapshot: () => ({
          status,
          dirty: appliedPrompts !== undefined,
          data: { quick_prompts: prompts },
        }),
      }),
      [status, appliedPrompts, prompts],
    );

    const summary = showPrompts
      ? status === "ready"
        ? t("experts.quickPromptsCount", {
            count: filterQuickPrompts(prompts).length,
          })
        : t(
            status === "loading"
              ? "common.loading"
              : "experts.quickPromptsLoadFailed",
          )
      : value?.trim() || t("experts.noWelcomeTitle");

    return (
      <ExpertConfigDrawer
        title={t("experts.pageConfigTitle")}
        summary={summary}
        open={open}
        disabled={disabled}
        onOpen={() => setOpen(true)}
        onClose={() => setOpen(false)}
        formId={formId}
      >
        {open && (
          <WelcomeEditor
            formId={formId}
            value={value}
            getName={() => String(parentForm.getFieldValue("name") ?? "")}
            editing={editing}
            kind={kind}
            status={status}
            showPrompts={showPrompts}
            prompts={prompts}
            onApply={(title, nextPrompts) => {
              if (title !== undefined) onChange?.(title);
              if (nextPrompts !== undefined) setAppliedPrompts(nextPrompts);
              setOpen(false);
            }}
          />
        )}
      </ExpertConfigDrawer>
    );
  },
);

WelcomeConfig.displayName = "WelcomeConfig";
export default WelcomeConfig;
