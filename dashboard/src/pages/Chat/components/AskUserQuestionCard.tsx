import { useMemo, useState } from "react";
import { Button, Input } from "antd";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { UserQuestionAnswer } from "../../../api/types/userQuestions";
import type { UserQuestionRequestData } from "../hooks/sseHelpers";
import styles from "../index.module.less";

interface DraftAnswer {
  selected: string[];
  custom: string;
  skipped: boolean;
}

interface AskUserQuestionCardProps {
  data: UserQuestionRequestData;
  onSubmit?: (pendingId: string, answers: UserQuestionAnswer[]) => void;
}

function displayOption(label: string): {
  label: string;
  recommended: boolean;
} {
  const suffix =
    /\s*(?:\((?:recommended|推荐)\)|（(?:recommended|推荐)）)\s*$/i;
  return {
    label: label.replace(suffix, ""),
    recommended: suffix.test(label),
  };
}

export default function AskUserQuestionCard({
  data,
  onSubmit,
}: AskUserQuestionCardProps) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const [drafts, setDrafts] = useState<DraftAnswer[]>(() =>
    data.questions.map(() => ({ selected: [], custom: "", skipped: false })),
  );
  const question = data.questions[index];
  const draft = drafts[index];
  const pending = data.status === "pending";

  const updateDraft = (next: DraftAnswer) => {
    setDrafts((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? next : item)),
    );
  };

  const choose = (label: string) => {
    if (!question || !draft || !pending) return;
    if (question.multi_select) {
      const selected = draft.selected.includes(label)
        ? draft.selected.filter((item) => item !== label)
        : [...draft.selected, label];
      updateDraft({ ...draft, selected, skipped: false });
      return;
    }
    updateDraft({ selected: [label], custom: "", skipped: false });
    if (index < data.questions.length - 1) setIndex(index + 1);
  };

  const answered = (value: DraftAnswer) =>
    value.skipped || value.selected.length > 0 || Boolean(value.custom.trim());
  const allAnswered = drafts.every(answered);

  const submit = (values = drafts) => {
    if (!onSubmit || !allAnswered) return;
    onSubmit(
      data.pendingId,
      data.questions.map((item, itemIndex) => {
        const value = values[itemIndex];
        const custom = value.custom.trim();
        return {
          id: item.id,
          selected: value.skipped
            ? []
            : custom && !item.multi_select
            ? []
            : value.selected,
          ...(custom ? { custom } : {}),
        };
      }),
    );
  };

  const continueFlow = () => {
    if (!draft || !answered(draft)) return;
    if (index < data.questions.length - 1) setIndex(index + 1);
    else submit();
  };

  const skip = () => {
    const next = drafts.map((item, itemIndex) =>
      itemIndex === index ? { selected: [], custom: "", skipped: true } : item,
    );
    setDrafts(next);
    if (index < data.questions.length - 1) setIndex(index + 1);
    else if (next.every(answered) && onSubmit) {
      onSubmit(
        data.pendingId,
        data.questions.map((item, itemIndex) => ({
          id: item.id,
          selected: next[itemIndex].selected,
          ...(next[itemIndex].custom.trim()
            ? { custom: next[itemIndex].custom.trim() }
            : {}),
        })),
      );
    }
  };

  const resolvedSummary = useMemo(() => {
    if (pending || !data.answers?.length) return "";
    return data.answers
      .map((answer) => answer.custom || answer.selected.join(", "))
      .filter(Boolean)
      .join(" · ");
  }, [data.answers, pending]);

  if (!question || !draft) return null;

  return (
    <section className={styles.askUserCard} aria-label={question.question}>
      <header className={styles.askUserHeader}>
        <div>
          {question.header ? (
            <div className={styles.askUserEyebrow}>{question.header}</div>
          ) : null}
          <div className={styles.askUserTitle}>{question.question}</div>
        </div>
        <div className={styles.askUserProgress}>
          {index + 1} / {data.questions.length}
        </div>
      </header>

      {pending ? (
        <div className={styles.askUserBody}>
          {question.options.map((option, optionIndex) => {
            const selected = draft.selected.includes(option.label);
            const display = displayOption(option.label);
            return (
              <button
                type="button"
                key={option.label}
                className={`${styles.askUserOption} ${
                  selected ? styles.askUserOptionSelected : ""
                }`}
                aria-pressed={selected}
                onClick={() => choose(option.label)}
              >
                <span className={styles.askUserOptionMarker}>
                  {question.multi_select && selected ? (
                    <Check size={13} />
                  ) : (
                    optionIndex + 1
                  )}
                </span>
                <span className={styles.askUserOptionCopy}>
                  <span>
                    {display.label}
                    {display.recommended ? (
                      <span className={styles.askUserRecommended}>
                        {t("chat.questions.recommended")}
                      </span>
                    ) : null}
                  </span>
                  {option.description ? (
                    <small>{option.description}</small>
                  ) : null}
                </span>
              </button>
            );
          })}
          <Input.TextArea
            className={styles.askUserCustom}
            autoSize={{ minRows: question.options.length ? 1 : 2, maxRows: 5 }}
            placeholder={t("chat.questions.customPlaceholder")}
            value={draft.custom}
            onChange={(event) =>
              updateDraft({
                selected: question.multi_select ? draft.selected : [],
                custom: event.target.value,
                skipped: false,
              })
            }
            onPressEnter={(event) => {
              if (event.shiftKey || event.nativeEvent.isComposing) return;
              event.preventDefault();
              continueFlow();
            }}
          />
        </div>
      ) : (
        <div className={styles.askUserResolved}>
          {resolvedSummary || t("chat.questions.skipped")}
        </div>
      )}

      {pending ? (
        <footer className={styles.askUserFooter}>
          <div className={styles.askUserPager}>
            <Button
              type="text"
              icon={<ChevronLeft size={15} />}
              disabled={index === 0}
              onClick={() => setIndex(index - 1)}
            />
            <Button
              type="text"
              icon={<ChevronRight size={15} />}
              disabled={index === data.questions.length - 1}
              onClick={() => setIndex(index + 1)}
            />
          </div>
          <div className={styles.askUserActions}>
            <Button onClick={skip}>{t("chat.questions.skip")}</Button>
            <Button
              type="primary"
              disabled={!answered(draft)}
              onClick={continueFlow}
            >
              {index === data.questions.length - 1
                ? t("chat.questions.submit")
                : t("chat.questions.next")}
            </Button>
          </div>
        </footer>
      ) : null}
    </section>
  );
}
