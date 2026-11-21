import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Input } from "antd";
import { Check } from "lucide-react";
import cx from "classnames";

import {
  BUILTIN_RUNNER_ORDER,
  isBuiltinRunner,
  runnerIcon,
  runnerIntroKey,
  runnerLabelKey,
} from "../../Agent/ACP/constants";
import styles from "../index.module.less";

function orderedRunners(runners: string[]): string[] {
  const enabled = new Set(runners);
  const builtins = BUILTIN_RUNNER_ORDER.filter((id) => enabled.has(id));
  const custom = runners
    .filter((id) => !isBuiltinRunner(id))
    .sort((left, right) => left.localeCompare(right));
  return [...builtins, ...custom];
}

/** Single-select runner cards: icon and title, same chrome as team members. */
export default function ManagedRunnerPicker({
  value,
  onChange,
  runners,
}: {
  value?: string;
  onChange?: (id: string) => void;
  runners: string[];
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const rows = useMemo(() => orderedRunners(runners), [runners]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter((id) => {
      const title = (
        isBuiltinRunner(id) ? t(runnerLabelKey(id)) : id
      ).toLowerCase();
      return title.includes(needle) || id.toLowerCase().includes(needle);
    });
  }, [query, rows, t]);

  return (
    <div className={styles.memberPicker}>
      <Input
        allowClear
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder={t("experts.managed.runnerSearch")}
      />
      {filtered.length === 0 ? (
        <div className={styles.memberPickerEmpty}>
          {rows.length === 0
            ? t("experts.managed.noRunners")
            : t("experts.managed.runnerSearchEmpty")}
        </div>
      ) : (
        <div className={styles.memberPickerGrid}>
          {filtered.map((id) => {
            const active = value === id;
            const title = isBuiltinRunner(id) ? t(runnerLabelKey(id)) : id;
            const intro = t(runnerIntroKey(id), { command: id });
            return (
              <button
                key={id}
                type="button"
                className={cx(
                  styles.memberPickCard,
                  active && styles.memberPickCardSelected,
                )}
                onClick={() => onChange?.(id)}
                aria-pressed={active}
              >
                {active ? (
                  <span className={styles.memberPickCheck} aria-hidden>
                    <Check size={11} strokeWidth={3} />
                  </span>
                ) : null}
                <div
                  className={styles.memberPickIcon}
                  style={{ background: "var(--fn-bg-secondary, #f5f5f5)" }}
                >
                  <img
                    src={runnerIcon(id)}
                    alt=""
                    className={cx(
                      styles.runnerPickImg,
                      id === "pi" && styles.invertOnDark,
                    )}
                  />
                </div>
                <div className={styles.memberPickBody}>
                  <div className={styles.memberPickName}>{title}</div>
                  <div className={styles.memberPickDesc}>{intro}</div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
