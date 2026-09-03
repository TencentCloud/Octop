import { Clock, Search, SquareMinus, SquarePlus } from "lucide-react";
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
  const searchLabel = t("chat.trajectoryToolbarSearch", "Search trajectory");
  const durationLabel = t("chat.trajectoryToolbarDuration", "Duration");
  const turnsLabel = t("chat.trajectoryToolbarTurns", "Turns");
  const callsLabel = t("chat.trajectoryToolbarCalls", "Calls");

  return (
    <div className={styles.root}>
      <div className={styles.toggles}>
        <button
          type="button"
          className={styles.switch}
          aria-pressed={durationOn}
          aria-label={durationLabel}
          onClick={() => onDurationOnChange(!durationOn)}
        >
          <Clock
            size={12}
            strokeWidth={1.75}
            aria-hidden
            className={styles.icon}
          />
          <span
            className={styles.switchTrack}
            data-on={durationOn ? "true" : "false"}
            aria-hidden
          >
            <span className={styles.switchThumb} />
          </span>
          <span>{durationLabel}</span>
        </button>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={allTurnsCollapsed}
          aria-label={turnsLabel}
          onClick={onToggleAllTurns}
        >
          {allTurnsCollapsed ? (
            <SquarePlus
              size={12}
              strokeWidth={1.75}
              aria-hidden
              className={styles.icon}
            />
          ) : (
            <SquareMinus
              size={12}
              strokeWidth={1.75}
              aria-hidden
              className={styles.icon}
            />
          )}
          <span>{turnsLabel}</span>
        </button>
        <button
          type="button"
          className={styles.toggle}
          aria-pressed={allCallsCollapsed}
          aria-label={callsLabel}
          onClick={onToggleAllCalls}
        >
          {allCallsCollapsed ? (
            <SquarePlus
              size={12}
              strokeWidth={1.75}
              aria-hidden
              className={styles.icon}
            />
          ) : (
            <SquareMinus
              size={12}
              strokeWidth={1.75}
              aria-hidden
              className={styles.icon}
            />
          )}
          <span>{callsLabel}</span>
        </button>
      </div>
      <label className={styles.search}>
        <Search
          size={12}
          strokeWidth={2}
          aria-hidden
          className={styles.searchIcon}
        />
        <input
          type="search"
          value={searchQuery}
          placeholder={searchLabel}
          aria-label={searchLabel}
          onChange={(event) => onSearchQueryChange(event.target.value)}
        />
      </label>
    </div>
  );
}
