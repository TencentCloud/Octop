import { useState } from "react";
import { Input } from "antd";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AskQuestion } from "../../../api/types/hitl";
import styles from "./AskQuestionCard.module.less";

const { TextArea } = Input;

/** Sentinel choice that reveals the free-text input for a question. */
const OTHER = "__other__";

const OPTION_KEYS = ["A", "B", "C", "D", "E", "F"] as const;

export interface AskQuestionCardProps {
  questions: AskQuestion[];
  status: "pending" | "approved" | "rejected";
  onSubmit?: (message: string) => void;
  /** Close the card without answering, ending the pause. */
  onDismiss?: () => void;
}

/** What the user picked for one question. */
type Answer = { picked: string[]; other: string };

/** Resolve one question's answer to display text, or `null` when unanswered. */
function answerText(question: AskQuestion, answer: Answer): string | null {
  const labels = answer.picked.filter((v) => v !== OTHER);
  const wantsOther = answer.picked.includes(OTHER) || !question.options?.length;
  const other = answer.other.trim();
  if (wantsOther && other) labels.push(other);
  if (!labels.length) return null;
  return labels.join("; ");
}

interface QuestionCardProps {
  question: AskQuestion;
  index: number;
  /** Stepped flow state for this question. */
  state: "done" | "current";
  answer: Answer;
  onAnswer: (answer: Answer, changed: string) => void;
}

function QuestionCard({
  question,
  index,
  state,
  answer,
  onAnswer,
}: QuestionCardProps) {
  const { t } = useTranslation();
  const options = question.options ?? [];
  const done = state === "done";
  const interactive = state === "current";
  const openEnded = options.length === 0;
  const hasOther = openEnded || answer.picked.includes(OTHER);

  const toggle = (label: string) => {
    if (!interactive) return;
    if (question.multi_select) {
      const picked = answer.picked.includes(label)
        ? answer.picked.filter((v) => v !== label)
        : [...answer.picked, label];
      onAnswer({ ...answer, picked }, label);
    } else {
      onAnswer({ ...answer, picked: [label] }, label);
    }
  };

  const confirmed = answerText(question, answer);

  return (
    <div className={styles.block}>
      <div className={styles.questionRow}>
        <span className={styles.qIndex}>{index + 1}.</span>
        <span className={styles.qText}>
          {question.header ? (
            <span className={styles.qHeader}>{question.header} · </span>
          ) : null}
          {question.question}
        </span>
      </div>

      {done && confirmed !== null ? (
        <div className={styles.doneAnswer}>{confirmed}</div>
      ) : (
        <div
          className={`${styles.options} ${interactive ? "" : styles.locked}`}
        >
          {options.map((option, optionIndex) => {
            const key = OPTION_KEYS[optionIndex] ?? String(optionIndex + 1);
            const selected = answer.picked.includes(option.label);
            return (
              <button
                key={option.label}
                type="button"
                className={`${styles.option} ${
                  selected ? styles.selected : ""
                }`}
                disabled={!interactive}
                onClick={() => toggle(option.label)}
              >
                <span className={styles.key}>{key}</span>
                <span className={styles.optionBody}>
                  <span className={styles.optionLabel}>{option.label}</span>
                  {option.description ? (
                    <span className={styles.optionDesc}>
                      {option.description}
                    </span>
                  ) : null}
                </span>
              </button>
            );
          })}
          {!openEnded ? (
            <button
              type="button"
              className={`${styles.option} ${hasOther ? styles.selected : ""}`}
              disabled={!interactive}
              onClick={() => toggle(OTHER)}
            >
              <span className={styles.key}>
                {options.length < OPTION_KEYS.length
                  ? OPTION_KEYS[options.length]
                  : ""}
              </span>
              <span className={styles.optionBody}>
                <span className={styles.optionLabel}>
                  {t("chat.ask.other")}
                </span>
              </span>
            </button>
          ) : null}
          {interactive && hasOther ? (
            <TextArea
              className={styles.freeText}
              autoSize={{ minRows: 1, maxRows: 4 }}
              value={answer.other}
              placeholder={t("chat.ask.freeTextPlaceholder")}
              onChange={(e) =>
                onAnswer({ ...answer, other: e.target.value }, OTHER)
              }
            />
          ) : null}
        </div>
      )}
    </div>
  );
}

function AskQuestionCard({
  questions,
  status,
  onSubmit,
  onDismiss,
}: AskQuestionCardProps) {
  const { t } = useTranslation();
  const interactive = status === "pending" && Boolean(onSubmit);
  const [answers, setAnswers] = useState<Answer[]>(() =>
    questions.map(() => ({ picked: [], other: "" })),
  );
  const [current, setCurrent] = useState(0);
  const [reviewing, setReviewing] = useState(false);

  const total = questions.length;
  const resolved = questions.map((q, i) => answerText(q, answers[i]));
  const currentAnswer = resolved[current];
  const isLast = current === total - 1;

  if (total === 0) return null;

  if (!interactive) {
    return (
      <details className={`${styles.card} ${styles.completedCard}`}>
        <summary className={styles.completedSummary}>
          <span className={styles.completedStatus}>
            {status === "approved"
              ? t("chat.ask.answeredSummary", { count: questions.length })
              : t("chat.ask.dismissedSummary", { count: questions.length })}
          </span>
          <span className={styles.expandHint}>{t("chat.ask.expand")}</span>
        </summary>
        <div className={styles.completedQuestions}>
          {questions.map((question, index) => (
            <div key={index} className={styles.block}>
              <div className={styles.questionRow}>
                <span className={styles.qIndex}>{index + 1}.</span>
                <span className={styles.qText}>{question.question}</span>
              </div>
            </div>
          ))}
        </div>
      </details>
    );
  }

  const advance = () => {
    if (isLast) {
      setReviewing(true);
    } else {
      setCurrent((c) => c + 1);
    }
  };

  const submit = () => {
    if (!onSubmit || resolved.some((text) => text === null)) return;
    const body = questions
      .map((q, i) => {
        const head = q.header?.trim() || q.question;
        return `${head}: ${resolved[i]}`;
      })
      .join("\n");
    onSubmit(body);
  };

  const skip = () => {
    onSubmit?.(t("chat.ask.skipMessage"));
  };

  const setAnswerAt = (index: number, answer: Answer, changed: string) => {
    setAnswers((prev) => prev.map((a, i) => (i === index ? answer : a)));
    // Single-select: picking a preset option is a commitment, so advance
    // straight to the next question. Multi-select needs explicit confirmation
    // to know when the user is done toggling; "other" needs free text.
    const question = questions[index];
    if (!question.multi_select && changed !== OTHER) {
      if (index === total - 1) {
        setReviewing(true);
      } else {
        setCurrent((c) => c + 1);
      }
    }
  };

  return (
    <div className={styles.card}>
      <div className={styles.titleRow}>
        <span className={styles.title}>{t("chat.ask.title")}</span>
        <span className={styles.titleActions}>
          <span className={styles.progress}>
            {reviewing ? t("chat.ask.reviewTag") : `${current + 1} / ${total}`}
          </span>
          {onDismiss ? (
            <button
              type="button"
              className={styles.closeButton}
              onClick={onDismiss}
              title={t("chat.ask.dismiss")}
              aria-label={t("chat.ask.dismiss")}
            >
              <X size={15} />
            </button>
          ) : null}
        </span>
      </div>

      <div className={styles.steps}>
        {reviewing ? (
          questions.map((question, index) => (
            <QuestionCard
              key={index}
              question={question}
              index={index}
              state="done"
              answer={answers[index]}
              onAnswer={(answer, changed) =>
                setAnswerAt(index, answer, changed)
              }
            />
          ))
        ) : (
          <QuestionCard
            key={current}
            question={questions[current]}
            index={current}
            state="current"
            answer={answers[current]}
            onAnswer={(answer, changed) =>
              setAnswerAt(current, answer, changed)
            }
          />
        )}
      </div>

      <div className={styles.actions}>
        {reviewing ? (
          <>
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryAction}`}
              onClick={submit}
            >
              {t("chat.ask.submit")}
            </button>
            <button
              type="button"
              className={`${styles.actionButton} ${styles.secondaryAction}`}
              onClick={() => setReviewing(false)}
            >
              {t("chat.ask.back")}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              className={`${styles.actionButton} ${styles.primaryAction}`}
              disabled={currentAnswer === null}
              onClick={advance}
            >
              {isLast ? t("chat.ask.review") : t("chat.ask.next")}
            </button>
            {current > 0 ? (
              <button
                type="button"
                className={`${styles.actionButton} ${styles.secondaryAction}`}
                onClick={() => setCurrent((value) => value - 1)}
              >
                {t("chat.ask.back")}
              </button>
            ) : null}
            <button
              type="button"
              className={`${styles.actionButton} ${styles.skipAction}`}
              onClick={skip}
            >
              {t("chat.ask.skip")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default AskQuestionCard;
