/**
 * `MetricsTab` — the 12-section snapshot, rendered by **what each number is worth**.
 *
 * `MetricSectionOut.state` (PLAN AM-26) is the whole point of this component:
 *
 * | state      | meaning                                            | how it renders |
 * |------------|----------------------------------------------------|----------------|
 * | `measured` | a real measurement                                 | the lines as-is |
 * | `proxy`    | a stand-in for an event family that does not exist | the lines **plus** a 代理标记 + the note |
 * | `empty`    | **no such event family yet**                       | **"暂无该事件族"**, never `0` |
 * | `partial`  | measured over an incomplete window                 | the lines plus a 不完整标记 |
 *
 * ★ The rule this component exists to enforce: **an empty section must never be
 * rendered as a measured `0`.** Silence would read as "no blockers", when the truth
 * may be "nobody registered them" (`sec`). Sections whose loader is still being wired
 * (T-47, `RollupSources` has no call site yet) arrive as `empty`/`proxy` and therefore
 * say so on screen.
 *
 * Presentational (AGENTS.md §5): no fetching — the caller owns the request.
 */

import { Alert, Empty, Tag, Typography } from "antd";
import { useTranslation } from "react-i18next";

import type {
  MetricSectionState,
  MetricsWire,
} from "../../../api/modules/teamRuns";

/** The three render modes the acceptance criterion requires to stay distinguishable. */
export type SectionMode = "measured" | "proxy" | "empty" | "partial";

export function sectionMode(state: MetricSectionState): SectionMode {
  switch (state) {
    case "measured":
    case "proxy":
    case "empty":
    case "partial":
      return state;
    default:
      // An unknown state must not silently pass as `measured` — treat it as
      // "we cannot claim anything", which is the honest default.
      return "empty";
  }
}

export interface MetricsTabProps {
  metrics: MetricsWire | null;
  loading?: boolean;
}

export default function MetricsTab({ metrics, loading }: MetricsTabProps) {
  const { t } = useTranslation();
  if (!metrics) {
    return (
      <Empty
        data-testid="metrics-empty-overall"
        description={
          loading
            ? t("teamRuns.metrics.loading")
            : t("teamRuns.metrics.notLoaded")
        }
      />
    );
  }
  return (
    <div data-testid="metrics-tab" className="flex flex-col gap-3">
      {metrics.sections.map((section) => {
        const mode = sectionMode(section.state);
        return (
          <div
            key={section.title}
            data-testid={`metric-${section.title}`}
            data-mode={mode}
          >
            <div className="flex items-center gap-2">
              <Typography.Text strong>{section.title}</Typography.Text>
              <Tag data-testid={`metric-state-${section.title}`}>{mode}</Tag>
            </div>
            {mode === "empty" ? (
              <Alert
                type="info"
                showIcon
                data-testid={`metric-empty-${section.title}`}
                message={t("teamRuns.metrics.eventFamilyMissing")}
                description={
                  section.note || t("teamRuns.metrics.eventFamilyMissingHint")
                }
              />
            ) : (
              <>
                {section.lines.map((line, index) => (
                  <div key={`${section.title}-${index}`} className="text-sm">
                    {line}
                  </div>
                ))}
                {mode === "proxy" ? (
                  <Typography.Text
                    type="secondary"
                    data-testid={`metric-proxy-${section.title}`}
                  >
                    {t("teamRuns.metrics.proxyHint")}
                    {section.note ? ` — ${section.note}` : ""}
                  </Typography.Text>
                ) : null}
                {mode === "partial" ? (
                  <Typography.Text
                    type="secondary"
                    data-testid={`metric-partial-${section.title}`}
                  >
                    {t("teamRuns.metrics.partialHint")}
                  </Typography.Text>
                ) : null}
                {section.lines.length === 0 ? (
                  // `measured`/`proxy` with no body: say "no data lines", do NOT print 0.
                  <Typography.Text
                    type="secondary"
                    data-testid={`metric-nolines-${section.title}`}
                  >
                    {t("teamRuns.metrics.noLines")}
                  </Typography.Text>
                ) : null}
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}
