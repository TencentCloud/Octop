import { useState, useEffect, useCallback } from "react";
import { Spin, Modal } from "antd";
import { message } from "@/utils/antdMessage";

import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { FlaskConical, Sparkles, Check } from "lucide-react";
import api from "../../../../api";
import type { MBTIType } from "../../../../api/types";
import { useAgent } from "../../../../context/AgentContext";
import MBTITest from "./MBTITest";
import styles from "./MBTISelector.module.less";

/* ------------------------------------------------------------------ */
/*  Dimension bar — horizontal axis visualisation                     */
/* ------------------------------------------------------------------ */

function DimensionBar({
  leftLabel,
  rightLabel,
  pole,
  pct,
  color,
}: {
  leftLabel: string;
  rightLabel: string;
  pole: string;
  pct: number;
  color: string;
}) {
  const isLeft = leftLabel.includes(pole);
  const position = isLeft ? 100 - pct : pct;

  return (
    <div className={styles.dimRow}>
      <span className={`${styles.dimLabel} ${isLeft ? styles.dimActive : ""}`}>
        {leftLabel}
      </span>
      <div className={styles.dimTrack}>
        <div
          className={styles.dimFill}
          style={{
            left: position < 50 ? `${position}%` : "50%",
            width: `${Math.abs(position - 50)}%`,
            background: color,
          }}
        />
        <div
          className={styles.dimDot}
          style={{ left: `${position}%`, background: color }}
        />
      </div>
      <span className={`${styles.dimLabel} ${!isLeft ? styles.dimActive : ""}`}>
        {rightLabel}
      </span>
      <span className={styles.dimPct}>{pct}%</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Right panel detail                                                */
/* ------------------------------------------------------------------ */

function TypeDetail({
  type,
  lang,
  onApply,
  applying,
}: {
  type: MBTIType;
  lang: "zh" | "en";
  onApply: () => void;
  applying: boolean;
}) {
  const { t } = useTranslation();
  const summary = lang === "zh" ? type.summary_zh : type.summary_en;
  const descriptors = lang === "zh" ? type.descriptors_zh : type.descriptors_en;

  const dims =
    lang === "zh"
      ? [
          {
            left: "E",
            right: "I",
            leftLabel: "外向 E",
            rightLabel: "I 内向",
            data: type.dimensions.ei,
          },
          {
            left: "S",
            right: "N",
            leftLabel: "感知 S",
            rightLabel: "N 直觉",
            data: type.dimensions.sn,
          },
          {
            left: "T",
            right: "F",
            leftLabel: "思维 T",
            rightLabel: "F 情感",
            data: type.dimensions.tf,
          },
          {
            left: "J",
            right: "P",
            leftLabel: "判断 J",
            rightLabel: "P 感知",
            data: type.dimensions.jp,
          },
        ]
      : [
          {
            left: "E",
            right: "I",
            leftLabel: "E",
            rightLabel: "I",
            data: type.dimensions.ei,
          },
          {
            left: "S",
            right: "N",
            leftLabel: "S",
            rightLabel: "N",
            data: type.dimensions.sn,
          },
          {
            left: "T",
            right: "F",
            leftLabel: "T",
            rightLabel: "F",
            data: type.dimensions.tf,
          },
          {
            left: "J",
            right: "P",
            leftLabel: "J",
            rightLabel: "P",
            data: type.dimensions.jp,
          },
        ];

  const behaviorKeys = [
    "answer_style",
    "casual_chat",
    "conflict",
    "creativity",
    "emotion",
    "planning",
  ] as const;
  const behaviorLabels: Record<string, string> =
    lang === "zh"
      ? {
          answer_style: "💬 回答风格",
          casual_chat: "☕ 闲聊画风",
          conflict: "⚡ 冲突应对",
          creativity: "💡 创造力",
          emotion: "🫶 情感回应",
          planning: "📋 规划方式",
        }
      : {
          answer_style: "Answer style",
          casual_chat: "Casual chat",
          conflict: "Conflict",
          creativity: "Creativity",
          emotion: "Emotion",
          planning: "Planning",
        };

  return (
    <div className={styles.detailContent}>
      {/* Scrollable body */}
      <div className={styles.detailBody}>
        {/* Summary */}
        <p className={styles.detailSummary}>{summary}</p>
        <div className={styles.detailTags}>
          {descriptors.split(/[、,]/).map((d) => (
            <span
              key={d.trim()}
              className={styles.detailTag}
              style={{ "--tag-color": type.color } as React.CSSProperties}
            >
              {d.trim()}
            </span>
          ))}
        </div>

        {/* Dimensions */}
        <div className={styles.detailSection}>
          <h4 className={styles.sectionTitle}>
            {t("personalization.mbti.dimensions")}
          </h4>
          {dims.map((d) => (
            <DimensionBar
              key={d.left}
              leftLabel={d.leftLabel}
              rightLabel={d.rightLabel}
              pole={d.data[0]}
              pct={d.data[1]}
              color={type.color}
            />
          ))}
        </div>

        {/* Behavior */}
        <div className={styles.detailSection}>
          <h4 className={styles.sectionTitle}>
            {t("personalization.mbti.behavior")}
          </h4>
          <div className={styles.behaviorGrid}>
            {behaviorKeys.map((key) => {
              const zhKey = `${key}_zh` as keyof typeof type.behavior;
              const value =
                lang === "zh" && type.behavior[zhKey]
                  ? type.behavior[zhKey]
                  : type.behavior[key];
              return (
                <div key={key} className={styles.behaviorItem}>
                  <span className={styles.behaviorLabel}>
                    {behaviorLabels[key]}
                  </span>
                  <span className={styles.behaviorValue}>{value}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Sticky apply button */}
      <div className={styles.detailFooter}>
        <button
          className={styles.applyButton}
          style={{ "--btn-color": type.color } as React.CSSProperties}
          onClick={onApply}
          disabled={applying}
        >
          {applying ? (
            <>{t("personalization.mbti.applying")}</>
          ) : (
            <>
              <Sparkles size={15} /> {t("personalization.mbti.applyType")}
            </>
          )}
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export default function MBTISelector({
  showHeader = true,
  showTestAction = false,
  testOpen: testOpenProp,
  onTestOpenChange,
  onApplied,
  agentId,
}: {
  showHeader?: boolean;
  /** When showHeader is false, still show the take-test button row. */
  showTestAction?: boolean;
  testOpen?: boolean;
  onTestOpenChange?: (open: boolean) => void;
  /** When provided, called after a successful apply instead of navigating to chat. */
  onApplied?: () => void;
  /** Target agent for MBTI apply/read; falls back to the global active agent. */
  agentId?: string;
}) {
  const { t, i18n } = useTranslation();
  const lang = (i18n.language === "zh" ? "zh" : "en") as "zh" | "en";
  const navigate = useNavigate();
  const { refresh: refreshAgents, activeAgentId } = useAgent();
  const targetAgentId = agentId ?? activeAgentId ?? undefined;

  const [types, setTypes] = useState<MBTIType[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedType, setSelectedType] = useState<MBTIType | null>(null);
  const [currentCode, setCurrentCode] = useState<string>("");
  const [applying, setApplying] = useState(false);
  const [testOpenInternal, setTestOpenInternal] = useState(false);

  const testOpen = testOpenProp ?? testOpenInternal;
  const setTestOpen = onTestOpenChange ?? setTestOpenInternal;

  useEffect(() => {
    if (!targetAgentId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([api.listMBTITypes(), api.getCurrentMBTI(targetAgentId)])
      .then(([allTypes, current]) => {
        setTypes(allTypes);
        if (current.configured && current.code) {
          setCurrentCode(current.code);
          // Don't auto-select on page load — wait for user click
        } else {
          setCurrentCode("");
        }
      })
      .catch(() => message.error(t("personalization.mbti.loadFailed")))
      .finally(() => setLoading(false));
  }, [t, targetAgentId]);

  const handleCardClick = useCallback((type: MBTIType) => {
    setSelectedType(type);
  }, []);

  const handleApply = useCallback(async () => {
    if (!selectedType || !targetAgentId) return;
    setApplying(true);
    try {
      await api.applyMBTIType(selectedType.code, lang, targetAgentId);
      void refreshAgents({ silent: true, force: true });
      if (onApplied) {
        setCurrentCode(selectedType.code);
        setSelectedType(null);
        onApplied();
      } else {
        const name =
          lang === "zh" ? selectedType.name_zh : selectedType.name_en;
        const pendingMsg =
          lang === "zh"
            ? `我刚刚把你的 MBTI 人格设定为了 ${selectedType.code}（${name}），快用你的新性格跟我打个招呼吧！`
            : `I just set your MBTI personality to ${selectedType.code} (${name}). Say hi with your new character!`;
        localStorage.setItem("octop.pendingChatMessage", pendingMsg);
        navigate("/chat");
        setTimeout(
          () =>
            window.dispatchEvent(new CustomEvent("octop:pending-chat-message")),
          100,
        );
      }
    } catch {
      message.error(t("personalization.mbti.applyFailed"));
    } finally {
      setApplying(false);
    }
  }, [
    selectedType,
    lang,
    t,
    navigate,
    onApplied,
    refreshAgents,
    targetAgentId,
  ]);

  const handleTestComplete = useCallback(
    (code: string) => {
      setTestOpen(false);
      const matched = types.find((t) => t.code === code);
      if (matched) setSelectedType(matched);
    },
    [types, setTestOpen],
  );

  if (loading) {
    return (
      <div className={styles.loadingState}>
        <Spin />
      </div>
    );
  }

  const groups = [
    { key: "analysts", codes: ["INTJ", "INTP", "ENTJ", "ENTP"] },
    { key: "diplomats", codes: ["INFJ", "INFP", "ENFJ", "ENFP"] },
    { key: "sentinels", codes: ["ISTJ", "ISFJ", "ESTJ", "ESFJ"] },
    { key: "explorers", codes: ["ISTP", "ISFP", "ESTP", "ESFP"] },
  ];
  const typeMap = new Map(types.map((t) => [t.code, t]));
  const currentType = currentCode ? typeMap.get(currentCode) : undefined;
  const currentLabel = currentType
    ? `${currentType.code} ${
        lang === "zh" ? currentType.name_zh : currentType.name_en
      }`
    : "";

  return (
    <div className={styles.mbtiSelector}>
      {showHeader && (
        <div className={styles.header}>
          <div>
            <h1 className={styles.headerTitle}>
              {t("personalization.mbti.title")}
            </h1>
            <p className={styles.subtitle}>
              {t("personalization.mbti.subtitle")}
            </p>
          </div>
          <button
            className={styles.testButton}
            onClick={() => setTestOpen(true)}
          >
            <FlaskConical size={14} />
            {t("personalization.mbti.takeTest")}
          </button>
        </div>
      )}

      <div className={styles.listToolbar}>
        <span className={styles.listToolbarMeta}>
          {t("personalization.mbti.listSummary", {
            total: types.length,
            selected: currentLabel,
            defaultValue: "当前有（{{total}}）个人格，已选中「{{selected}}」",
          })}
        </span>
        {!showHeader && showTestAction && (
          <button
            className={styles.testButton}
            onClick={() => setTestOpen(true)}
          >
            <FlaskConical size={14} />
            {t("personalization.mbti.takeTest")}
          </button>
        )}
      </div>

      {/* Cards only — no detail panel */}
      <div className={styles.cardsArea}>
        {groups.map((group) => (
          <div key={group.key} className={styles.group}>
            <div className={styles.groupLabel}>
              {t(`personalization.mbti.group.${group.key}`)}
            </div>
            <div className={styles.typeGrid}>
              {group.codes.map((code) => {
                const type = typeMap.get(code);
                if (!type) return null;
                const name = lang === "zh" ? type.name_zh : type.name_en;
                const summary =
                  lang === "zh" ? type.summary_zh : type.summary_en;
                const isSelected = selectedType?.code === code;
                const isCurrent = currentCode === code;
                const dimAxes =
                  lang === "zh"
                    ? [
                        {
                          leftLabel: "外向 E",
                          rightLabel: "I 内向",
                          data: type.dimensions.ei,
                        },
                        {
                          leftLabel: "感知 S",
                          rightLabel: "N 直觉",
                          data: type.dimensions.sn,
                        },
                        {
                          leftLabel: "思维 T",
                          rightLabel: "F 情感",
                          data: type.dimensions.tf,
                        },
                        {
                          leftLabel: "判断 J",
                          rightLabel: "P 感知",
                          data: type.dimensions.jp,
                        },
                      ]
                    : [
                        {
                          leftLabel: "E",
                          rightLabel: "I",
                          data: type.dimensions.ei,
                        },
                        {
                          leftLabel: "S",
                          rightLabel: "N",
                          data: type.dimensions.sn,
                        },
                        {
                          leftLabel: "T",
                          rightLabel: "F",
                          data: type.dimensions.tf,
                        },
                        {
                          leftLabel: "J",
                          rightLabel: "P",
                          data: type.dimensions.jp,
                        },
                      ];
                return (
                  <div
                    key={code}
                    className={`${styles.typeCard} ${
                      isSelected ? styles.typeCardSelected : ""
                    } ${isCurrent ? styles.typeCardCurrent : ""}`}
                    style={
                      { "--card-color": type.color } as React.CSSProperties
                    }
                    onClick={() => handleCardClick(type)}
                    role="button"
                    tabIndex={0}
                  >
                    <div
                      className={styles.typeCardAccent}
                      style={{
                        background:
                          isSelected || isCurrent
                            ? type.color
                            : `${type.color}88`,
                      }}
                    />
                    <div className={styles.typeCardBody}>
                      <div className={styles.typeCardHeader}>
                        <img
                          className={styles.typeAvatar}
                          src={`/assets/mbti/${code}.svg`}
                          alt={code}
                          style={{ background: `${type.color}14` }}
                        />
                        <div className={styles.typeCardMeta}>
                          <div className={styles.typeCardName}>
                            <span style={{ color: type.color }}>
                              {type.code}
                            </span>{" "}
                            {name}
                            {isCurrent && (
                              <span
                                className={styles.currentBadge}
                                style={
                                  {
                                    "--badge-color": type.color,
                                  } as React.CSSProperties
                                }
                              >
                                <Check size={11} />{" "}
                                {lang === "zh" ? "当前" : "Active"}
                              </span>
                            )}
                          </div>
                          {lang === "zh" && type.nickname_zh && (
                            <div className={styles.typeNickname}>
                              {type.nickname_zh}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className={styles.typeDesc}>{summary}</div>
                      <div className={styles.typeDims}>
                        {dimAxes.map((axis) => (
                          <DimensionBar
                            key={axis.leftLabel}
                            leftLabel={axis.leftLabel}
                            rightLabel={axis.rightLabel}
                            pole={axis.data[0]}
                            pct={axis.data[1]}
                            color={type.color}
                          />
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Modal for detail view */}
      <Modal
        open={!!selectedType}
        onCancel={() => setSelectedType(null)}
        width={560}
        destroyOnHidden
        footer={null}
        closable
        className={styles.mbtiModal}
        style={
          {
            "--modal-color": selectedType?.color || "#000",
          } as React.CSSProperties
        }
      >
        {selectedType && (
          <>
            <div
              className={styles.modalHeader}
              style={{ background: selectedType.color }}
            >
              <div className={styles.modalHeaderInner}>
                <img
                  className={styles.modalAvatar}
                  src={`/assets/mbti/${selectedType.code}.svg`}
                  alt={selectedType.code}
                />
                <div>
                  <div className={styles.modalCode}>{selectedType.code}</div>
                  <div className={styles.modalName}>
                    {lang === "zh"
                      ? selectedType.name_zh
                      : selectedType.name_en}
                    {lang === "zh" && selectedType.nickname_zh && (
                      <span style={{ opacity: 0.75, marginLeft: 6 }}>
                        「{selectedType.nickname_zh}」
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div className={styles.modalBody}>
              <TypeDetail
                type={selectedType}
                lang={lang}
                onApply={handleApply}
                applying={applying}
              />
            </div>
          </>
        )}
      </Modal>

      {/* Test modal */}
      <MBTITest
        open={testOpen}
        onClose={() => setTestOpen(false)}
        onComplete={handleTestComplete}
        agentId={targetAgentId}
      />
    </div>
  );
}
