import { useState, useEffect, useCallback } from "react";
import { Modal, message } from "antd";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, AlertTriangle } from "lucide-react";
import api from "../../../../api";
import type { MBTITestQuestion, MBTIType } from "../../../../api/types";
import styles from "./MBTITest.module.less";

type Stage = "intro" | "questions" | "result";

interface MBTITestProps {
  open: boolean;
  onClose: () => void;
  onComplete: (code: string) => void;
  agentId?: string;
}

/* ------------------------------------------------------------------ */
/*  Result card (shown at the end)                                    */
/* ------------------------------------------------------------------ */

function ResultCard({
  code,
  profile,
  dimensions,
  lang,
  onApply,
  applying,
}: {
  code: string;
  profile: MBTIType;
  dimensions: {
    ei: [string, number];
    sn: [string, number];
    tf: [string, number];
    jp: [string, number];
  };
  lang: "zh" | "en";
  onApply: () => void;
  applying: boolean;
}) {
  const { t } = useTranslation();
  const name = lang === "zh" ? profile.name_zh : profile.name_en;
  const summary = lang === "zh" ? profile.summary_zh : profile.summary_en;

  const axes = [
    { label: "E/I", data: dimensions.ei },
    { label: "S/N", data: dimensions.sn },
    { label: "T/F", data: dimensions.tf },
    { label: "J/P", data: dimensions.jp },
  ];

  return (
    <div className={styles.resultCard}>
      <div
        className={styles.resultHeader}
        style={{ background: profile.color }}
      >
        <img
          className={styles.resultAvatar}
          src={`/assets/mbti/${code}.svg`}
          alt={code}
        />
        <div className={styles.resultCode}>{code}</div>
        <div className={styles.resultName}>{name}</div>
      </div>
      <p className={styles.resultSummary}>{summary}</p>

      <div className={styles.resultDims}>
        {axes.map((a) => (
          <div key={a.label} className={styles.resultDimRow}>
            <span className={styles.resultDimLabel}>{a.label}</span>
            <div className={styles.resultDimBar}>
              <div
                className={styles.resultDimFill}
                style={{
                  width: `${a.data[1]}%`,
                  background: profile.color,
                }}
              />
            </div>
            <span className={styles.resultDimValue}>
              {a.data[0]} {a.data[1]}%
            </span>
          </div>
        ))}
      </div>

      <div className={styles.disclaimer}>
        <AlertTriangle size={14} />
        <span>{t("personalization.mbti.disclaimer")}</span>
      </div>

      <button
        className={styles.resultApplyBtn}
        style={{ background: profile.color }}
        onClick={onApply}
        disabled={applying}
      >
        {applying
          ? t("personalization.mbti.applying")
          : t("personalization.mbti.applyResult")}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main test component                                               */
/* ------------------------------------------------------------------ */

export default function MBTITest({
  open,
  onClose,
  onComplete,
  agentId,
}: MBTITestProps) {
  const { t, i18n } = useTranslation();
  const lang = (i18n.language === "zh" ? "zh" : "en") as "zh" | "en";
  const navigate = useNavigate();

  const [stage, setStage] = useState<Stage>("intro");
  const [questions, setQuestions] = useState<MBTITestQuestion[]>([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{
    code: string;
    profile: MBTIType;
    dimensions: {
      ei: [string, number];
      sn: [string, number];
      tf: [string, number];
      jp: [string, number];
    };
  } | null>(null);
  const [applying, setApplying] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Load questions
  useEffect(() => {
    if (open) {
      api
        .getMBTITestQuestions()
        .then(setQuestions)
        .catch(() => message.error("Failed to load questions"));
    }
  }, [open]);

  // Reset when closing
  useEffect(() => {
    if (!open) {
      setStage("intro");
      setCurrentIdx(0);
      setAnswers({});
      setResult(null);
    }
  }, [open]);

  const handleAnswer = useCallback(
    (choice: "A" | "B") => {
      const q = questions[currentIdx];
      if (!q) return;
      setAnswers((prev) => ({ ...prev, [String(q.id)]: choice }));

      // Auto-advance
      if (currentIdx < questions.length - 1) {
        setTimeout(() => setCurrentIdx((i) => i + 1), 200);
      }
    },
    [currentIdx, questions],
  );

  const handleSubmit = useCallback(async () => {
    setSubmitting(true);
    try {
      const res = await api.submitMBTITest(answers, false, lang);
      setResult({
        code: res.code,
        profile: res.profile,
        dimensions: res.dimensions,
      });
      setStage("result");
    } catch {
      message.error(t("personalization.mbti.submitFailed"));
    } finally {
      setSubmitting(false);
    }
  }, [answers, lang, t]);

  const handleApply = useCallback(async () => {
    if (!result || !agentId) return;
    setApplying(true);
    try {
      await api.applyMBTIType(result.code, lang, agentId);
      const name =
        lang === "zh" ? result.profile.name_zh : result.profile.name_en;
      const pendingMsg =
        lang === "zh"
          ? `我刚刚把你的 MBTI 人格设定为了 ${result.code}（${name}），快用你的新性格跟我打个招呼吧！`
          : `I just set your MBTI personality to ${result.code} (${name}). Say hi with your new character!`;
      localStorage.setItem("octop.pendingChatMessage", pendingMsg);
      onComplete(result.code);
      navigate("/chat");
      setTimeout(
        () =>
          window.dispatchEvent(new CustomEvent("octop:pending-chat-message")),
        100,
      );
    } catch {
      message.error(t("personalization.mbti.applyFailed"));
    } finally {
      setApplying(false);
    }
  }, [result, lang, t, onComplete, navigate, agentId]);

  const answeredCount = Object.keys(answers).length;
  const allAnswered =
    answeredCount === questions.length && questions.length > 0;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={560}
      styles={{ body: { padding: 0, minHeight: 400 } }}
      destroyOnHidden
      closable={stage !== "questions"}
    >
      {stage === "intro" && (
        <div className={styles.intro}>
          <div className={styles.introIcon}>🧠</div>
          <h2 className={styles.introTitle}>
            {t("personalization.mbti.testTitle")}
          </h2>
          <p className={styles.introDesc}>
            {t("personalization.mbti.testIntro")}
          </p>
          <div className={styles.disclaimer}>
            <AlertTriangle size={14} />
            <span>{t("personalization.mbti.disclaimer")}</span>
          </div>
          <button
            className={styles.startBtn}
            onClick={() => setStage("questions")}
            disabled={questions.length === 0}
          >
            {t("personalization.mbti.startTest")}
          </button>
        </div>
      )}

      {stage === "questions" && questions.length > 0 && (
        <div className={styles.questionPage}>
          {/* Progress bar */}
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{ width: `${(answeredCount / questions.length) * 100}%` }}
            />
          </div>

          <div className={styles.progressText}>
            {answeredCount} / {questions.length}
          </div>

          {/* Answer sheet — clickable dot grid */}
          <div className={styles.answerSheet}>
            {questions.map((q, idx) => {
              const answered = !!answers[String(q.id)];
              const isCurrent = idx === currentIdx;
              return (
                <button
                  key={q.id}
                  className={`${styles.answerDot} ${
                    answered ? styles.answerDotDone : ""
                  } ${isCurrent ? styles.answerDotCurrent : ""}`}
                  onClick={() => setCurrentIdx(idx)}
                  title={`${idx + 1}`}
                >
                  {idx + 1}
                </button>
              );
            })}
          </div>

          {/* Question */}
          {(() => {
            const q = questions[currentIdx];
            const questionText = lang === "zh" ? q.question_zh : q.question_en;
            const optionA = lang === "zh" ? q.option_a_zh : q.option_a_en;
            const optionB = lang === "zh" ? q.option_b_zh : q.option_b_en;
            const currentAnswer = answers[String(q.id)];

            return (
              <div className={styles.questionContent}>
                <h3 className={styles.questionText}>{questionText}</h3>

                <div className={styles.options}>
                  <button
                    className={`${styles.optionBtn} ${
                      currentAnswer === "A" ? styles.selected : ""
                    }`}
                    onClick={() => handleAnswer("A")}
                  >
                    <span className={styles.optionLetter}>A</span>
                    <span>{optionA}</span>
                  </button>
                  <button
                    className={`${styles.optionBtn} ${
                      currentAnswer === "B" ? styles.selected : ""
                    }`}
                    onClick={() => handleAnswer("B")}
                  >
                    <span className={styles.optionLetter}>B</span>
                    <span>{optionB}</span>
                  </button>
                </div>
              </div>
            );
          })()}

          {/* Navigation */}
          <div className={styles.navRow}>
            <button
              className={styles.navBtn}
              onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))}
              disabled={currentIdx === 0}
            >
              <ChevronLeft size={16} />
              {t("personalization.mbti.prev")}
            </button>

            <button
              className={styles.submitBtn}
              onClick={() => {
                if (!allAnswered) {
                  const remaining = questions.length - answeredCount;
                  message.warning(
                    lang === "zh"
                      ? `还有 ${remaining} 题没答完哦，去答题卡看看哪些漏了~`
                      : `${remaining} question${
                          remaining > 1 ? "s" : ""
                        } remaining. Check the answer sheet above!`,
                  );
                  // Jump to first unanswered
                  const firstUnanswered = questions.findIndex(
                    (q) => !answers[String(q.id)],
                  );
                  if (firstUnanswered >= 0) setCurrentIdx(firstUnanswered);
                  return;
                }
                handleSubmit();
              }}
              disabled={submitting}
            >
              {submitting
                ? t("personalization.mbti.submitting")
                : allAnswered
                ? t("personalization.mbti.viewResult")
                : `${t("personalization.mbti.submit")} (${answeredCount}/${
                    questions.length
                  })`}
            </button>

            <button
              className={styles.navBtn}
              onClick={() =>
                setCurrentIdx((i) => Math.min(questions.length - 1, i + 1))
              }
              disabled={currentIdx === questions.length - 1}
            >
              {t("personalization.mbti.next")}
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {stage === "result" && result && (
        <ResultCard
          code={result.code}
          profile={result.profile}
          dimensions={result.dimensions}
          lang={lang}
          onApply={handleApply}
          applying={applying}
        />
      )}
    </Modal>
  );
}
