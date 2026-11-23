import { useCallback, useMemo, useState } from "react";
import { Popover } from "antd";
import cx from "classnames";
import { ChevronDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import styles from "./RegionPicker.module.less";

export type CloudRegion = { id: string; name: string };

interface RegionPickerProps {
  regions: CloudRegion[];
  /** 每个地域的节点数（`region` → 实例数量）。 */
  counts: Record<string, number>;
  /** 已选地域 id，空数组表示"全部地域"。 */
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

interface RegionItem {
  id: string;
  short: string;
  area: string;
  count: number;
}

const RECENT_KEY = "octop:cloud:recent-regions";
const RECENT_MAX = 6;

/** 大区排序：与腾讯云控制台地域选择器一致，未命中的排在末尾。 */
const AREA_ORDER = [
  "华南地区",
  "华东地区",
  "华北地区",
  "华中地区",
  "西南地区",
  "西北地区",
  "东北地区",
  "港澳台地区",
  "亚太东南",
  "亚太东北",
  "亚太南部",
  "欧洲地区",
  "北美地区",
  "南美地区",
  "中东地区",
  "非洲地区",
];

/** "华南地区（广州 OPEN）" → { area: "华南地区", short: "广州 OPEN" } */
function parseRegionName(
  name: string,
  id: string,
): { area: string; short: string } {
  const match = /^\s*(.+?)\s*[（(](.+?)[)）]\s*$/.exec(name ?? "");
  if (match) {
    return { area: match[1].trim(), short: match[2].trim() };
  }
  return { area: "", short: (name || id).trim() };
}

function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function writeRecent(ids: string[]) {
  try {
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(ids));
  } catch {
    // 隐私模式 / 配额满：只是便利功能，失败不影响筛选
  }
}

export default function RegionPicker({
  regions,
  counts,
  value,
  onChange,
  disabled = false,
}: RegionPickerProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [recent, setRecent] = useState<string[]>(readRecent);

  const items = useMemo<RegionItem[]>(
    () =>
      regions.map((region) => {
        const { area, short } = parseRegionName(region.name, region.id);
        return { id: region.id, short, area, count: counts[region.id] ?? 0 };
      }),
    [regions, counts],
  );

  const groups = useMemo(() => {
    const map = new Map<string, RegionItem[]>();
    for (const item of items) {
      const bucket = map.get(item.area);
      if (bucket) bucket.push(item);
      else map.set(item.area, [item]);
    }
    return [...map.entries()]
      .map(([area, list]) => ({
        area,
        label: area || t("cloud.regionOtherArea", "其他地区"),
        items: list,
      }))
      .sort((a, b) => {
        const ia = AREA_ORDER.indexOf(a.area);
        const ib = AREA_ORDER.indexOf(b.area);
        return (
          (ia < 0 ? AREA_ORDER.length : ia) - (ib < 0 ? AREA_ORDER.length : ib)
        );
      });
  }, [items, t]);

  const recentItems = useMemo(
    () =>
      recent
        .map((id) => items.find((item) => item.id === id))
        .filter((item): item is RegionItem => Boolean(item))
        .slice(0, RECENT_MAX),
    [recent, items],
  );

  const selected = useMemo(
    () => items.filter((item) => value.includes(item.id)),
    [items, value],
  );
  const totalCount = useMemo(
    () => items.reduce((sum, item) => sum + item.count, 0),
    [items],
  );
  const selectedCount = selected.reduce((sum, item) => sum + item.count, 0);
  const restCount = Math.max(0, totalCount - selectedCount);

  const toggle = useCallback(
    (id: string) => {
      const next = value.includes(id)
        ? value.filter((item) => item !== id)
        : [...value, id];
      onChange(next);
      setRecent((prev) => {
        const merged = [id, ...prev.filter((item) => item !== id)].slice(
          0,
          RECENT_MAX,
        );
        writeRecent(merged);
        return merged;
      });
    },
    [onChange, value],
  );

  const triggerLabel =
    selected.length === 0
      ? t("cloud.regionAll", "全部地域")
      : selected.length === 1
      ? selected[0].short
      : t("cloud.regionSelectedMulti", {
          name: selected[0].short,
          count: selected.length,
          defaultValue: "{{name}} 等 {{count}} 个",
        });

  const renderItem = (item: RegionItem, extraClass?: string) => {
    const active = value.includes(item.id);
    return (
      <button
        key={item.id}
        type="button"
        className={cx(styles.item, extraClass, active && styles.itemActive)}
        aria-pressed={active}
        title={`${item.short} · ${item.id}`}
        onClick={() => toggle(item.id)}
      >
        <span className={styles.itemName}>{item.short}</span>
        {item.count > 0 ? (
          <>
            <span className={styles.itemCount}>{item.count}</span>
            <span className={styles.itemDot} aria-hidden />
          </>
        ) : null}
      </button>
    );
  };

  const body = (
    <div className={styles.body}>
      {recentItems.length > 0 ? (
        <div className={styles.section}>
          <div className={styles.sectionTitle}>
            {t("cloud.regionRecent", "最近访问")}
          </div>
          <div className={styles.recentRow}>
            {recentItems.map((item) => renderItem(item, styles.recentItem))}
          </div>
        </div>
      ) : null}

      <div className={styles.section}>
        <div className={styles.sectionTitle}>
          {t("cloud.regionAllAreas", "全部地区")}
        </div>
        <div className={styles.areas}>
          {groups.map((group) => (
            <div key={group.area || "_other"} className={styles.area}>
              <div className={styles.areaTitle}>{group.label}</div>
              <div className={styles.areaItems}>
                {group.items.map((item) => renderItem(item))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {value.length > 0 ? (
        <div className={styles.footer}>
          <span className={styles.footerText}>
            {t("cloud.regionSelectedTotal", {
              count: value.length,
              defaultValue: "已选 {{count}} 个地域",
            })}
          </span>
          <button
            type="button"
            className={styles.clearBtn}
            onClick={() => onChange([])}
          >
            {t("cloud.regionClear", "清空筛选")}
          </button>
        </div>
      ) : null}
    </div>
  );

  return (
    <Popover
      trigger="click"
      placement="bottomLeft"
      open={open && !disabled}
      onOpenChange={(next) => setOpen(disabled ? false : next)}
      overlayClassName={styles.popover}
      content={body}
      arrow={false}
    >
      <button
        type="button"
        className={cx(styles.trigger, disabled && styles.triggerDisabled)}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open && !disabled}
      >
        <span className={styles.triggerMain}>
          <span className={styles.triggerLabel}>{triggerLabel}</span>
          {selected.length > 0 && selectedCount > 0 ? (
            <>
              <span className={styles.triggerCount}>{selectedCount}</span>
              <span className={styles.triggerDot} aria-hidden />
            </>
          ) : null}
        </span>
        {selected.length > 0 && restCount > 0 ? (
          <span className={styles.triggerRest}>
            {t("cloud.regionOthers", {
              count: restCount,
              defaultValue: "其它地域({{count}})",
            })}
          </span>
        ) : null}
        <ChevronDown
          size={12}
          className={cx(styles.caret, open && !disabled && styles.caretOpen)}
        />
      </button>
    </Popover>
  );
}
