import { useTranslation } from "react-i18next";
import styles from "./TrajectoryToolbar.module.less";

export interface TrajectoryToolbarProps {
  durationOn: boolean;
  onDurationOnChange: (next: boolean) => void;
  allTurnsCollapsed: boolean;
  onToggleAllTurns: () => void;
  allCallsCollapsed: boolean;
  onToggleAllCalls: () => void;
  searchQuery: string;
  onSearchQueryChange: (query: string) => void;
}

export default function TrajectoryToolbar({
  durationOn,
  onDurationOnChange,
  allTurnsCollapsed,
  onToggleAllTurns,
  allCallsCollapsed,
  onToggleAllCalls,
  searchQuery,
  onSearchQueryChange,
}: TrajectoryToolbarProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.root}>
      <div className={styles.toggles}>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={durationOn}
          onClick={() => onDurationOnChange(!durationOn)}
        >
          {t("chat.trajectoryToolbarDuration", "Duration")}
        </button>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={allTurnsCollapsed}
          onClick={onToggleAllTurns}
        >
          {t("chat.trajectoryToolbarTurns", "Turns")}
        </button>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={allCallsCollapsed}
          onClick={onToggleAllCalls}
        >
          {t("chat.trajectoryToolbarCalls", "Calls")}
        </button>
      </div>
      <input
        type="search"
        className={styles.search}
        value={searchQuery}
        placeholder={t("chat.trajectoryToolbarSearch", "Search trajectory")}
        aria-label={t("chat.trajectoryToolbarSearch", "Search trajectory")}
        onChange={(event) => onSearchQueryChange(event.target.value)}
      />
    </div>
  );
}
