import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Button, ConfigProvider, Tooltip } from "antd";
import {
  AppWindow,
  GripHorizontal,
  PanelBottom,
  PanelRight,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import styles from "./AssistantFrame.module.less";

export type AssistantPlacement = "right" | "bottom" | "float";

function placementLabel(placement: AssistantPlacement): [string, string] {
  if (placement === "bottom") return ["assistant.dockBottom", "停靠在底部"];
  if (placement === "right") return ["assistant.dockRight", "停靠在右侧"];
  return ["assistant.undock", "取消停靠"];
}

function placementIcon(placement: AssistantPlacement) {
  if (placement === "bottom") return <PanelBottom size={14} />;
  if (placement === "right") return <PanelRight size={14} />;
  return <AppWindow size={14} />;
}

type ResizeDir = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

const FLOAT_DIRS: ResizeDir[] = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
const MARGIN = 8;
const MIN_FLOAT_W = 320;
const MIN_FLOAT_H = 360;
const MIN_DOCK_W = 280;
const MIN_DOCK_H = 200;

type Geo = {
  x: number;
  y: number;
  w: number;
  h: number;
  dockW: number;
  dockH: number;
};

export function readAssistantPlacement(
  key: string,
  fallback: AssistantPlacement,
): AssistantPlacement {
  try {
    const raw = localStorage.getItem(key);
    if (raw === "right" || raw === "bottom" || raw === "float") return raw;
  } catch {
    /* 隐私模式等读不到本地存储时用默认值 */
  }
  return fallback;
}

function defaultGeo(dockW = 400): Geo {
  return {
    x: Math.max(MARGIN, window.innerWidth - 424),
    y: 88,
    w: 400,
    h: Math.min(680, window.innerHeight - 140),
    dockW,
    dockH: 300,
  };
}

function loadGeo(
  storageKey: string,
  legacy?: { widthKey?: string; heightKey?: string },
  dockW?: number,
): Geo {
  const fallback = defaultGeo(dockW);
  try {
    const raw = localStorage.getItem(`${storageKey}:geo`);
    if (raw) return { ...fallback, ...(JSON.parse(raw) as Partial<Geo>) };
    if (legacy?.widthKey) {
      const width = parseInt(localStorage.getItem(legacy.widthKey) || "", 10);
      if (Number.isFinite(width)) fallback.dockW = width;
    }
    if (legacy?.heightKey) {
      const height = parseInt(localStorage.getItem(legacy.heightKey) || "", 10);
      if (Number.isFinite(height)) fallback.dockH = height;
    }
  } catch {
    /* 坏数据直接用默认尺寸 */
  }
  return fallback;
}

function limits() {
  return {
    w: Math.max(MIN_FLOAT_W, window.innerWidth - MARGIN * 2),
    h: Math.max(MIN_FLOAT_H, window.innerHeight - MARGIN * 2),
  };
}

function clamp(x: number, y: number, w: number, h: number) {
  return {
    x: Math.min(
      Math.max(MARGIN, x),
      Math.max(MARGIN, window.innerWidth - w - MARGIN),
    ),
    y: Math.min(
      Math.max(MARGIN, y),
      Math.max(MARGIN, window.innerHeight - h - MARGIN),
    ),
  };
}

export default function AssistantFrame({
  placement,
  onPlacementChange,
  placementKey,
  storageKey,
  legacySize,
  dock = "inline",
  defaultDockWidth = 400,
  placementLocked = false,
  placements,
  hidden = false,
  title,
  headerExtra,
  onClose,
  children,
  bodyClassName,
}: {
  placement: AssistantPlacement;
  onPlacementChange: (next: AssistantPlacement) => void;
  /** 停靠方式的本地存储键，和页面布局共用。 */
  placementKey: string;
  /** 尺寸的本地存储键。 */
  storageKey: string;
  legacySize?: { widthKey?: string; heightKey?: string };
  /** inline 参与页面分栏；overlay 固定在视口边缘。 */
  dock?: "inline" | "overlay";
  /** 第一次打开右侧栏时的宽度。已记住的尺寸优先。 */
  defaultDockWidth?: number;
  placementLocked?: boolean;
  /**
   * 列出可选摆放。不传时只保留「右侧停靠 / 取消停靠」一个开关。
   * 终端需要底部、右侧和取消停靠三个按钮。
   */
  placements?: readonly AssistantPlacement[];
  /** 页签收起时不渲染。父组件保持挂载，回来仍是原来的会话。 */
  hidden?: boolean;
  title: ReactNode;
  headerExtra?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  bodyClassName?: string;
}) {
  const { t } = useTranslation();
  const frameRef = useRef<HTMLDivElement>(null);
  const [geo, setGeo] = useState<Geo>(() =>
    loadGeo(storageKey, legacySize, defaultDockWidth),
  );
  const geoRef = useRef(geo);
  geoRef.current = geo;
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    origX: number;
    origY: number;
    moved: boolean;
  } | null>(null);
  const sizeRef = useRef<{
    dir: ResizeDir;
    pointerId: number;
    startX: number;
    startY: number;
    orig: Geo;
  } | null>(null);

  const floating = placement === "float";
  const overlay = dock === "overlay" || floating;

  const persist = useCallback(
    (next: Geo) => {
      geoRef.current = next;
      setGeo(next);
      try {
        localStorage.setItem(`${storageKey}:geo`, JSON.stringify(next));
      } catch {
        /* 忽略写入失败 */
      }
    },
    [storageKey],
  );

  const choose = (next: AssistantPlacement) => {
    if (placementLocked || next === placement) return;
    try {
      localStorage.setItem(placementKey, next);
    } catch {
      /* 忽略写入失败 */
    }
    onPlacementChange(next);
  };

  const onHeaderPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!floating || event.button !== 0) return;
    if (
      (event.target as HTMLElement).closest(
        "button, input, textarea, a, select, [role='combobox'], [role='menu'], [role='menuitem']",
      )
    ) {
      return;
    }
    const rect = frameRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origX: rect.left,
      origY: rect.top,
      moved: false,
    };
  };

  const onResizePointerDown =
    (dir: ResizeDir) => (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      sizeRef.current = {
        dir,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        orig: geoRef.current,
      };
    };

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (drag && event.pointerId === drag.pointerId) {
        const dx = event.clientX - drag.startX;
        const dy = event.clientY - drag.startY;
        if (!drag.moved && Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
        drag.moved = true;
        const next = clamp(
          drag.origX + dx,
          drag.origY + dy,
          geoRef.current.w,
          geoRef.current.h,
        );
        persist({ ...geoRef.current, ...next });
        return;
      }
      const resize = sizeRef.current;
      if (!resize || event.pointerId !== resize.pointerId) return;
      const dx = event.clientX - resize.startX;
      const dy = event.clientY - resize.startY;
      const cap = limits();
      if (floating) {
        let { x, y, w, h } = resize.orig;
        if (resize.dir.includes("e")) w += dx;
        if (resize.dir.includes("s")) h += dy;
        if (resize.dir.includes("w")) {
          w -= dx;
          x += dx;
        }
        if (resize.dir.includes("n")) {
          h -= dy;
          y += dy;
        }
        w = Math.min(Math.max(MIN_FLOAT_W, w), cap.w);
        h = Math.min(Math.max(MIN_FLOAT_H, h), cap.h);
        if (resize.dir.includes("w")) x = resize.orig.x + (resize.orig.w - w);
        if (resize.dir.includes("n")) y = resize.orig.y + (resize.orig.h - h);
        persist({ ...geoRef.current, w, h, ...clamp(x, y, w, h) });
        return;
      }
      if (placement === "right") {
        const dockW = Math.min(
          Math.max(MIN_DOCK_W, resize.orig.dockW - dx),
          Math.min(720, window.innerWidth - 160),
        );
        persist({ ...geoRef.current, dockW });
        return;
      }
      const dockH = Math.min(
        Math.max(MIN_DOCK_H, resize.orig.dockH - dy),
        Math.min(640, window.innerHeight - 120),
      );
      persist({ ...geoRef.current, dockH });
    };
    const onUp = (event: PointerEvent) => {
      if (dragRef.current?.pointerId === event.pointerId)
        dragRef.current = null;
      if (sizeRef.current?.pointerId === event.pointerId)
        sizeRef.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [floating, persist, placement]);

  useEffect(() => {
    if (!floating) return undefined;
    const onResize = () => {
      const cap = limits();
      const w = Math.min(geoRef.current.w, cap.w);
      const h = Math.min(geoRef.current.h, cap.h);
      persist({
        ...geoRef.current,
        w,
        h,
        ...clamp(geoRef.current.x, geoRef.current.y, w, h),
      });
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [floating, persist]);

  if (hidden) return null;

  const dirs = floating
    ? FLOAT_DIRS
    : placement === "right"
    ? (["w"] as ResizeDir[])
    : (["n"] as ResizeDir[]);
  const shell = (
    <>
      {dirs.map((dir) => (
        <div
          key={dir}
          className={floating ? styles.floatHandle : styles.dockHandle}
          data-dir={dir}
          onPointerDown={onResizePointerDown(dir)}
        />
      ))}
      <div className={overlay ? styles.glass : styles.dockShell}>
        <div
          className={styles.header}
          data-float={floating ? "1" : "0"}
          onPointerDown={onHeaderPointerDown}
        >
          <span className={styles.title}>
            {floating ? (
              <GripHorizontal size={14} className={styles.grip} />
            ) : null}
            <span className={styles.titleText}>{title}</span>
          </span>
          <span className={styles.actions}>
            {headerExtra}
            {placementLocked ? null : placements ? (
              placements.map((item) => (
                <Tooltip key={item} title={t(...placementLabel(item))}>
                  <Button
                    size="small"
                    type="text"
                    className={
                      placement === item ? styles.activeAction : undefined
                    }
                    aria-pressed={placement === item}
                    icon={placementIcon(item)}
                    onClick={() => choose(item)}
                  />
                </Tooltip>
              ))
            ) : (
              <Tooltip
                title={
                  placement === "right"
                    ? t("assistant.undock", "取消停靠")
                    : t("assistant.dockRight", "停靠在右侧")
                }
              >
                <Button
                  size="small"
                  type="text"
                  className={
                    placement === "right" ? styles.activeAction : undefined
                  }
                  aria-pressed={placement === "right"}
                  icon={<PanelRight size={14} />}
                  onClick={() =>
                    choose(placement === "right" ? "float" : "right")
                  }
                />
              </Tooltip>
            )}
            <Button
              size="small"
              type="text"
              aria-label={t("common.close", "关闭")}
              icon={<X size={14} />}
              onClick={onClose}
            />
          </span>
        </div>
        <div className={`${styles.body} ${bodyClassName ?? ""}`}>
          {children}
        </div>
      </div>
    </>
  );

  const frame = floating ? (
    <div
      ref={frameRef}
      className={styles.float}
      style={{ left: geo.x, top: geo.y, width: geo.w, height: geo.h }}
    >
      {shell}
    </div>
  ) : dock === "overlay" ? (
    <div
      ref={frameRef}
      className={
        placement === "right" ? styles.overlayRight : styles.overlayBottom
      }
      style={
        placement === "right" ? { width: geo.dockW } : { height: geo.dockH }
      }
    >
      {shell}
    </div>
  ) : (
    <div
      ref={frameRef}
      className={
        placement === "right" ? styles.inlineRight : styles.inlineBottom
      }
      style={
        placement === "right" ? { width: geo.dockW } : { height: geo.dockH }
      }
    >
      {shell}
    </div>
  );

  // 下拉和选择器默认叠在 1050，会落到浮动窗下面。
  const hosted = (
    <ConfigProvider theme={{ token: { zIndexPopupBase: 2000 } }}>
      {frame}
    </ConfigProvider>
  );

  return overlay ? createPortal(hosted, document.body) : hosted;
}
