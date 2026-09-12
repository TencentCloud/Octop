/**
 * In-app PDF viewer via Mozilla PDF.js (react-pdf) — avoids Chrome's iframe
 * chrome and keeps look/controls consistent across browsers.
 *
 * Pages render windowed: only pages near the scroll viewport mount
 * ``<Page>`` (canvas + text + annotation layers); the rest stay as
 * size-accurate placeholders. Once mounted, pages stay mounted while
 * near the current page so scroll remounts do not leave blank canvases.
 * Mounting every page of a large PDF at once floods the DOM (one canvas
 * + two layers per page) and makes scrolling repaint constantly.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button, Drawer, Tooltip } from "antd";
import {
  ListTree,
  Maximize2,
  Minus,
  Plus,
  RotateCcw,
  Scan,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { Document, Page, pdfjs } from "react-pdf";
import type { PDFDocumentProxy } from "pdfjs-dist";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { useIsMobile } from "../hooks/useIsMobile";
import styles from "./PdfDocumentPreview.module.less";
import DocumentPreviewLoading from "./DocumentPreviewLoading";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const MIN_ZOOM = 0.5;
const MAX_ZOOM = 2.5;
const ZOOM_STEP = 0.1;
/** height / width ratio fallback (A4 portrait) until real page sizes load. */
const DEFAULT_PAGE_RATIO = 1.4142;
/** Eagerly measure this many page ratios on open (rest fill as you scroll). */
const RATIO_EAGER_PAGES = 32;
/** Extra pages around the visible window to measure ratios for. */
const RATIO_WINDOW = 4;
/** Pages within this band of the viewport get mounted; outside, placeholder. */
const VISIBLE_ROOT_MARGIN = "600px 0px";
/**
 * Keep ``<Page>`` mounted within this many pages of ``currentPage`` even after
 * the slot leaves the IO root. Remounting react-pdf canvases on every scroll
 * often paints blank until a full remount/reload.
 */
const MOUNT_KEEP_RADIUS = 2;
/** Boot overlay fade-out before unmount (ms). */
const BOOT_FADE_MS = 180;

type FitMode = "width" | "page" | "manual";

interface PdfDocumentPreviewProps {
  fileUrl: string;
  filename: string;
}

/** PDF.js outline (bookmark) tree node. */
export interface PdfOutlineItem {
  title: string;
  dest: string | unknown[] | null;
  url?: string | null;
  items?: PdfOutlineItem[];
}

/** Structural subset of ``PDFDocumentProxy`` this viewer needs. */
type PdfDocumentLike = Pick<
  PDFDocumentProxy,
  "numPages" | "getPage" | "getOutline" | "getDestination" | "getPageIndex"
>;

async function measurePageRatio(
  pdf: PdfDocumentLike,
  pageNo: number,
): Promise<number> {
  try {
    const page = await pdf.getPage(pageNo);
    const viewport = page.getViewport({ scale: 1 });
    return viewport.width > 0
      ? viewport.height / viewport.width
      : DEFAULT_PAGE_RATIO;
  } catch {
    return DEFAULT_PAGE_RATIO;
  }
}

/** Resolve a bookmark destination (named or explicit) to a 1-based page. */
async function outlineDestPage(
  pdf: PdfDocumentLike,
  dest: string | unknown[] | null,
): Promise<number | null> {
  if (!dest) return null;
  try {
    const explicit =
      typeof dest === "string" ? await pdf.getDestination(dest) : dest;
    if (!Array.isArray(explicit) || explicit.length === 0) return null;
    const index = await pdf.getPageIndex(explicit[0]);
    return Number.isFinite(index) ? index + 1 : null;
  } catch {
    return null;
  }
}

function walkOutline(
  items: PdfOutlineItem[],
  visit: (item: PdfOutlineItem) => void,
): void {
  for (const item of items) {
    visit(item);
    if (item.items && item.items.length > 0) walkOutline(item.items, visit);
  }
}

/** Nearest outline item whose dest page is <= current (or exact match). */
function activeOutlineItem(
  items: PdfOutlineItem[],
  currentPage: number,
  destPages: Map<PdfOutlineItem, number | null>,
): PdfOutlineItem | null {
  let best: PdfOutlineItem | null = null;
  let bestPage = 0;
  walkOutline(items, (item) => {
    const page = destPages.get(item);
    if (page == null || page > currentPage || page < bestPage) return;
    best = item;
    bestPage = page;
  });
  return best;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return (
    target.closest("input, textarea, select, [contenteditable='true']") != null
  );
}

const supportsIntersectionObserver =
  typeof IntersectionObserver !== "undefined";

/** Thin top progress bar: real percent while downloading, sliding
 *  (indeterminate) while pdf.js parses. */
function PdfLoadingBar({ percent }: { percent?: number | null }) {
  const clamped =
    percent != null && Number.isFinite(percent)
      ? Math.max(2, Math.min(100, Math.round(percent)))
      : null;
  return (
    <div className={styles.pdfLoadingBar} aria-hidden>
      <div
        className={
          clamped != null
            ? styles.pdfLoadingBarFill
            : styles.pdfLoadingBarIndeterminate
        }
        style={clamped != null ? { width: clamped + "%" } : undefined}
      />
    </div>
  );
}

/** Clean paper placeholder (no fake text lines) shared by skeletons. */
function SkelPage() {
  return <div className={styles.skelPage} aria-hidden />;
}

/** In-slot page placeholder for unmounted pages and Page loading. */
function PdfPageSkeletonBlock() {
  return <div className={styles.pdfPageSkeleton} aria-hidden />;
}

/** Merge intersecting slots with pages kept near the reading position. */
function stickyMountedPages(
  intersecting: ReadonlySet<number>,
  previouslyMounted: ReadonlySet<number>,
  currentPage: number,
  keepRadius: number,
): Set<number> {
  const next = new Set<number>();
  for (const pageNo of intersecting) next.add(pageNo);
  for (const pageNo of previouslyMounted) {
    if (Math.abs(pageNo - currentPage) <= keepRadius) next.add(pageNo);
  }
  if (currentPage > 0) next.add(currentPage);
  return next;
}

function samePageSet(a: ReadonlySet<number>, b: ReadonlySet<number>): boolean {
  if (a.size !== b.size) return false;
  for (const pageNo of a) {
    if (!b.has(pageNo)) return false;
  }
  return true;
}

/** Full viewer skeleton + real download percent, shown while the blob loads. */
export function PdfViewerSkeleton({ percent }: { percent?: number | null }) {
  return (
    <div className={styles.pdfPreview} aria-busy="true">
      <div className={styles.pdfToolbar}>
        <PdfLoadingBar percent={percent} />
      </div>
      <div className={styles.pdfScroll}>
        <SkelPage />
        <SkelPage />
      </div>
    </div>
  );
}

export default function PdfDocumentPreview({
  fileUrl,
  filename,
}: PdfDocumentPreviewProps) {
  const { t } = useTranslation();
  const isMobile = useIsMobile();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const hoveredRef = useRef(false);
  const [numPages, setNumPages] = useState(0);
  const [pageWidth, setPageWidth] = useState(720);
  const [zoom, setZoom] = useState(1);
  const [fitMode, setFitMode] = useState<FitMode>("width");
  const [loadFailed, setLoadFailed] = useState(false);
  const [docReady, setDocReady] = useState(false);
  const [firstPageReady, setFirstPageReady] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  /** height / width ratio per page at scale 1 — exact placeholder heights. */
  const [pageRatios, setPageRatios] = useState<number[]>([]);
  /** Pages whose ratios were measured from pdf.js (vs default placeholder). */
  const measuredRatioPagesRef = useRef(new Set<number>());
  /** Slots currently intersecting the padded scroll root. */
  const intersectingRef = useRef<Set<number>>(new Set());
  /** Pages with a mounted ``<Page>`` (sticky around current page). */
  const mountedRef = useRef<Set<number>>(new Set());
  const [visiblePages, setVisiblePages] = useState<ReadonlySet<number>>(
    () => new Set<number>(),
  );
  const [currentPage, setCurrentPage] = useState(1);
  const currentPageRef = useRef(1);
  currentPageRef.current = currentPage;
  const [pageInput, setPageInput] = useState("1");
  const pageInputFocusedRef = useRef(false);
  /** Loaded PDF instance — kept for lazy bookmark destination resolution. */
  const pdfRef = useRef<PdfDocumentLike | null>(null);
  /** Bookmark tree; ``null`` until fetched (``[]`` means the PDF has none). */
  const [outline, setOutline] = useState<PdfOutlineItem[] | null>(null);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const destPageCacheRef = useRef(new Map<PdfOutlineItem, number | null>());
  const [outlineDestVersion, setOutlineDestVersion] = useState(0);
  const [bootOverlayMounted, setBootOverlayMounted] = useState(true);
  const [bootOverlayFading, setBootOverlayFading] = useState(false);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const measure = () => {
      const next = Math.floor(el.clientWidth - 32);
      if (next <= 0) return;
      setPageWidth((prev) => (next === prev ? prev : next));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Reset viewer state when the file CHANGES — skip the mount run so a
  // fast (effect-time) onLoadSuccess cannot race the reset below.
  const mountedFileUrlRef = useRef(fileUrl);
  useEffect(() => {
    if (mountedFileUrlRef.current === fileUrl) return;
    mountedFileUrlRef.current = fileUrl;
    setNumPages(0);
    setLoadFailed(false);
    setZoom(1);
    setFitMode("width");
    setDocReady(false);
    setFirstPageReady(false);
    setPageRatios([]);
    measuredRatioPagesRef.current = new Set();
    setCurrentPage(1);
    setPageInput("1");
    setReloadKey(0);
    intersectingRef.current = new Set();
    mountedRef.current = new Set();
    setVisiblePages(new Set());
    pdfRef.current = null;
    setOutline(null);
    setOutlineOpen(false);
    destPageCacheRef.current = new Map();
    setOutlineDestVersion(0);
    setBootOverlayMounted(true);
    setBootOverlayFading(false);
    const el = scrollRef.current;
    if (el) el.scrollTop = 0;
  }, [fileUrl]);

  // Track intersecting slots; keep ``<Page>`` sticky near the current page so
  // scroll remounts do not leave blank react-pdf canvases.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || numPages === 0 || !supportsIntersectionObserver) return;
    const io = new IntersectionObserver(
      (entries) => {
        const intersecting = new Set(intersectingRef.current);
        let intersectingChanged = false;
        for (const entry of entries) {
          const pageNo = Number((entry.target as HTMLElement).dataset.pdfPage);
          if (!Number.isFinite(pageNo) || pageNo <= 0) continue;
          if (entry.isIntersecting) {
            if (!intersecting.has(pageNo)) {
              intersecting.add(pageNo);
              intersectingChanged = true;
            }
          } else if (intersecting.has(pageNo)) {
            intersecting.delete(pageNo);
            intersectingChanged = true;
          }
        }
        if (!intersectingChanged) return;
        intersectingRef.current = intersecting;
        const next = stickyMountedPages(
          intersecting,
          mountedRef.current,
          currentPageRef.current,
          MOUNT_KEEP_RADIUS,
        );
        if (samePageSet(next, mountedRef.current)) return;
        mountedRef.current = next;
        setVisiblePages(next);
      },
      { root: el, rootMargin: VISIBLE_ROOT_MARGIN },
    );
    for (const node of el.querySelectorAll<HTMLElement>("[data-pdf-page]")) {
      io.observe(node);
    }
    return () => io.disconnect();
  }, [numPages]);

  // When the reading page moves, drop far sticky mounts outside the keep band.
  useEffect(() => {
    if (numPages === 0) return;
    const next = stickyMountedPages(
      intersectingRef.current,
      mountedRef.current,
      currentPage,
      MOUNT_KEEP_RADIUS,
    );
    if (samePageSet(next, mountedRef.current)) return;
    mountedRef.current = next;
    setVisiblePages(next);
  }, [currentPage, numPages]);

  // Current page = most visible slot (highest intersection ratio, else closest to top).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || numPages === 0 || !supportsIntersectionObserver) return;
    const ratios = new Map<number, number>();
    const tops = new Map<number, number>();
    const pick = () => {
      let bestPage = 0;
      let bestRatio = -1;
      let bestTopDist = Number.POSITIVE_INFINITY;
      const rootTop = el.getBoundingClientRect().top;
      for (const [pageNo, ratio] of ratios) {
        const top = tops.get(pageNo) ?? rootTop;
        const topDist = Math.abs(top - rootTop);
        if (
          ratio > bestRatio + 0.001 ||
          (Math.abs(ratio - bestRatio) <= 0.001 && topDist < bestTopDist)
        ) {
          bestRatio = ratio;
          bestTopDist = topDist;
          bestPage = pageNo;
        }
      }
      if (bestPage > 0) {
        setCurrentPage((prev) => (prev === bestPage ? prev : bestPage));
      }
    };
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const pageNo = Number((entry.target as HTMLElement).dataset.pdfPage);
          if (!Number.isFinite(pageNo) || pageNo <= 0) continue;
          if (entry.isIntersecting && entry.intersectionRatio > 0) {
            ratios.set(pageNo, entry.intersectionRatio);
            tops.set(pageNo, entry.boundingClientRect.top);
          } else {
            ratios.delete(pageNo);
            tops.delete(pageNo);
          }
        }
        pick();
      },
      {
        root: el,
        threshold: [0, 0.1, 0.25, 0.5, 0.75, 1],
      },
    );
    for (const node of el.querySelectorAll<HTMLElement>("[data-pdf-page]")) {
      io.observe(node);
    }
    return () => io.disconnect();
  }, [numPages]);

  useEffect(() => {
    if (pageInputFocusedRef.current) return;
    setPageInput(String(currentPage));
  }, [currentPage]);

  const handleLoadSuccess = useCallback((pdf: PdfDocumentLike) => {
    pdfRef.current = pdf;
    setNumPages(pdf.numPages);
    setDocReady(true);
    setLoadFailed(false);
    setOutline(null);
    setOutlineOpen(false);
    destPageCacheRef.current = new Map();
    setOutlineDestVersion(0);
    // Mount page 1 immediately so the first canvas can paint under the
    // boot overlay (windowed IO otherwise leaves every slot empty).
    if (pdf.numPages > 0) {
      intersectingRef.current = new Set([1]);
      mountedRef.current = new Set([1]);
      setVisiblePages(new Set([1]));
      setCurrentPage(1);
      setPageInput("1");
    } else {
      setFirstPageReady(true);
    }
    pdf
      .getOutline()
      .then(async (items) => {
        const tree = items ?? [];
        setOutline(tree);
        // Keep outline closed by default — especially on narrow widths.
        // Prefetch dest pages so outline active highlight can resolve.
        const cache = destPageCacheRef.current;
        const tasks: Promise<void>[] = [];
        walkOutline(tree, (item) => {
          if (item.url || !item.dest || cache.has(item)) return;
          tasks.push(
            outlineDestPage(pdf, item.dest).then((page) => {
              cache.set(item, page);
            }),
          );
        });
        if (tasks.length > 0) {
          await Promise.all(tasks);
          setOutlineDestVersion((v) => v + 1);
        }
      })
      .catch(() => setOutline([]));
    // Seed defaults so slots have stable heights, then measure eagerly for
    // the first band and fill the rest as the user scrolls (large PDFs).
    setPageRatios(
      Array.from({ length: pdf.numPages }, () => DEFAULT_PAGE_RATIO),
    );
    measuredRatioPagesRef.current = new Set();
    const eagerCount = Math.min(pdf.numPages, RATIO_EAGER_PAGES);
    if (eagerCount > 0) {
      void Promise.all(
        Array.from({ length: eagerCount }, (_, index) =>
          measurePageRatio(pdf, index + 1),
        ),
      ).then((ratios) => {
        if (pdfRef.current !== pdf) return;
        for (let i = 1; i <= eagerCount; i += 1) {
          measuredRatioPagesRef.current.add(i);
        }
        setPageRatios((prev) => {
          if (prev.length !== pdf.numPages) return prev;
          const next = prev.slice();
          ratios.forEach((ratio, index) => {
            next[index] = ratio;
          });
          return next;
        });
      });
    }
  }, []);

  // Fill page aspect ratios around the visible window (and current page).
  useEffect(() => {
    const pdf = pdfRef.current;
    if (!pdf || numPages === 0) return;
    const want = new Set<number>();
    for (const pageNo of visiblePages) {
      for (let delta = -RATIO_WINDOW; delta <= RATIO_WINDOW; delta += 1) {
        const next = pageNo + delta;
        if (next >= 1 && next <= numPages) want.add(next);
      }
    }
    for (let delta = -RATIO_WINDOW; delta <= RATIO_WINDOW; delta += 1) {
      const next = currentPage + delta;
      if (next >= 1 && next <= numPages) want.add(next);
    }
    const missing = Array.from(want).filter(
      (pageNo) => !measuredRatioPagesRef.current.has(pageNo),
    );
    if (missing.length === 0) return;
    let cancelled = false;
    void Promise.all(
      missing.map(async (pageNo) => {
        const ratio = await measurePageRatio(pdf, pageNo);
        return [pageNo, ratio] as const;
      }),
    ).then((results) => {
      if (cancelled || pdfRef.current !== pdf) return;
      for (const [pageNo] of results) {
        measuredRatioPagesRef.current.add(pageNo);
      }
      setPageRatios((prev) => {
        if (prev.length !== numPages) return prev;
        const next = prev.slice();
        for (const [pageNo, ratio] of results) {
          next[pageNo - 1] = ratio;
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [visiblePages, currentPage, numPages]);

  const renderWidth = Math.max(120, Math.floor(pageWidth * zoom));
  const ratioFor = (pageNo: number) =>
    pageRatios[pageNo - 1] ?? DEFAULT_PAGE_RATIO;
  const bootLoading = !loadFailed && (!docReady || !firstPageReady);

  // Fade boot overlay out, then unmount — interactions unblocked as soon as fade starts.
  useEffect(() => {
    if (bootLoading) {
      setBootOverlayMounted(true);
      setBootOverlayFading(false);
      return;
    }
    setBootOverlayFading(true);
    const timer = window.setTimeout(() => {
      setBootOverlayMounted(false);
      setBootOverlayFading(false);
    }, BOOT_FADE_MS);
    return () => window.clearTimeout(timer);
  }, [bootLoading]);

  const applyFitZoom = useCallback(
    (mode: Exclude<FitMode, "manual">) => {
      const el = scrollRef.current;
      if (!el || pageWidth <= 0) return;
      if (mode === "width") {
        setZoom(1);
        return;
      }
      // Fit page: scale so the current page's full height fits the scroll viewport.
      const availableH = Math.max(80, el.clientHeight - 32);
      const ratio =
        pageRatios[currentPageRef.current - 1] ?? DEFAULT_PAGE_RATIO;
      const pageHAtFitWidth = pageWidth * ratio;
      if (pageHAtFitWidth <= 0) return;
      const next = Math.min(
        MAX_ZOOM,
        Math.max(MIN_ZOOM, availableH / pageHAtFitWidth),
      );
      setZoom((prev) =>
        Math.abs(prev - next) < 0.001 ? prev : Math.round(next * 100) / 100,
      );
    },
    [pageWidth, pageRatios],
  );

  useEffect(() => {
    if (fitMode === "manual" || numPages === 0 || bootLoading) return;
    applyFitZoom(fitMode);
  }, [fitMode, applyFitZoom, numPages, bootLoading]);

  const scrollToPage = useCallback(
    (pageNo: number) => {
      if (pageNo < 1 || pageNo > numPages) return;
      const el = scrollRef.current?.querySelector<HTMLElement>(
        `[data-pdf-page="${pageNo}"]`,
      );
      // Instant jump: smooth scrolling over dozens of windowed placeholders
      // (whose heights refine as ratios load) drags and re-targets mid-flight.
      el?.scrollIntoView({ behavior: "auto", block: "start" });
      setCurrentPage(pageNo);
      setPageInput(String(pageNo));
    },
    [numPages],
  );

  const commitPageInput = useCallback(() => {
    const parsed = Number.parseInt(pageInput.trim(), 10);
    if (!Number.isFinite(parsed) || numPages <= 0) {
      setPageInput(String(currentPage));
      return;
    }
    const clamped = Math.min(numPages, Math.max(1, parsed));
    scrollToPage(clamped);
  }, [pageInput, numPages, currentPage, scrollToPage]);

  const bumpZoom = useCallback((next: number) => {
    setFitMode("manual");
    setZoom(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next)));
  }, []);

  const handleRetry = useCallback(() => {
    setLoadFailed(false);
    setDocReady(false);
    setFirstPageReady(false);
    setNumPages(0);
    setPageRatios([]);
    measuredRatioPagesRef.current = new Set();
    setCurrentPage(1);
    setPageInput("1");
    setOutline(null);
    setOutlineOpen(false);
    pdfRef.current = null;
    destPageCacheRef.current = new Map();
    setOutlineDestVersion(0);
    intersectingRef.current = new Set();
    mountedRef.current = new Set();
    setVisiblePages(new Set());
    setBootOverlayMounted(true);
    setBootOverlayFading(false);
    setReloadKey((k) => k + 1);
  }, []);

  const goToOutlineItem = useCallback(
    async (item: PdfOutlineItem) => {
      if (item.url) {
        window.open(item.url, "_blank", "noopener,noreferrer");
        return;
      }
      const pdf = pdfRef.current;
      if (!pdf || !item.dest) return;
      const cache = destPageCacheRef.current;
      if (!cache.has(item)) {
        cache.set(item, await outlineDestPage(pdf, item.dest));
        setOutlineDestVersion((v) => v + 1);
      }
      const pageNo = cache.get(item);
      if (pageNo) scrollToPage(pageNo);
      if (isMobile) setOutlineOpen(false);
    },
    [scrollToPage, isMobile],
  );

  const activeOutline = useMemo(() => {
    if (!outline || outline.length === 0) return null;
    return activeOutlineItem(outline, currentPage, destPageCacheRef.current);
  }, [outline, currentPage, outlineDestVersion]);

  const renderOutline = useCallback(
    (items: PdfOutlineItem[], depth: number): ReactNode =>
      items.map((item, index) => {
        const isActive = item === activeOutline;
        const className = isActive
          ? `${styles.pdfOutlineItem} ${styles.pdfOutlineItemActive}`
          : styles.pdfOutlineItem;
        return (
          <div key={`${depth}-${index}`}>
            {item.url ? (
              <a
                className={className}
                style={{ paddingLeft: 10 + depth * 14 }}
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                title={item.title}
              >
                {item.title}
              </a>
            ) : (
              <button
                type="button"
                className={className}
                style={{ paddingLeft: 10 + depth * 14 }}
                title={item.title}
                aria-current={isActive ? "true" : undefined}
                onClick={() => void goToOutlineItem(item)}
              >
                {item.title}
              </button>
            )}
            {item.items && item.items.length > 0
              ? renderOutline(item.items, depth + 1)
              : null}
          </div>
        );
      }),
    [goToOutlineItem, activeOutline],
  );

  // Keyboard when root is focused or hovered — do not steal keys from inputs.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (isEditableTarget(e.target)) return;
      const root = rootRef.current;
      if (!root) return;
      const focusInside =
        document.activeElement != null && root.contains(document.activeElement);
      if (!hoveredRef.current && !focusInside) return;
      if (numPages <= 0 || bootLoading) return;
      let next: number | null = null;
      switch (e.key) {
        case "ArrowLeft":
        case "PageUp":
          next = Math.max(1, currentPage - 1);
          break;
        case "ArrowRight":
        case "PageDown":
          next = Math.min(numPages, currentPage + 1);
          break;
        case "Home":
          next = 1;
          break;
        case "End":
          next = numPages;
          break;
        default:
          return;
      }
      e.preventDefault();
      if (next !== currentPage) scrollToPage(next);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [numPages, bootLoading, currentPage, scrollToPage]);

  return (
    <div
      ref={rootRef}
      className={styles.pdfPreview}
      tabIndex={0}
      onMouseEnter={() => {
        hoveredRef.current = true;
      }}
      onMouseLeave={() => {
        hoveredRef.current = false;
      }}
    >
      <div className={styles.pdfToolbar}>
        <div className={styles.pdfToolbarGroup}>
          <Tooltip
            title={
              outline !== null && outline.length === 0
                ? t("workspace.pdfOutlineEmpty", "This document has no outline")
                : t("workspace.pdfOutline", "Outline")
            }
          >
            <span className={styles.pdfOutlineToggleHost}>
              <Button
                type="text"
                size="small"
                icon={<ListTree size={14} />}
                aria-label={t("workspace.pdfOutline", "Outline")}
                disabled={!outline || outline.length === 0}
                onClick={() => setOutlineOpen((v) => !v)}
              />
            </span>
          </Tooltip>
          {numPages > 0 ? (
            <span className={styles.pdfPageIndicator}>
              <input
                className={styles.pdfPageInput}
                type="text"
                inputMode="numeric"
                aria-label={t("workspace.pdfGoToPage", "Go to page")}
                value={pageInput}
                disabled={bootLoading}
                onFocus={() => {
                  pageInputFocusedRef.current = true;
                }}
                onChange={(e) => setPageInput(e.target.value)}
                onBlur={() => {
                  pageInputFocusedRef.current = false;
                  commitPageInput();
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    (e.target as HTMLInputElement).blur();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    setPageInput(String(currentPage));
                    (e.target as HTMLInputElement).blur();
                  }
                }}
              />
              <span className={styles.pdfPageSep} aria-hidden>
                /
              </span>
              <span className={styles.pdfPageTotal}>{numPages}</span>
            </span>
          ) : null}
          <Button
            type="text"
            size="small"
            icon={<Minus size={14} />}
            aria-label={t("workspace.pdfZoomOut", "Zoom out")}
            disabled={zoom <= MIN_ZOOM || bootLoading}
            onClick={() => bumpZoom(zoom - ZOOM_STEP)}
          />
          <span className={styles.pdfZoomLabel}>{Math.round(zoom * 100)}%</span>
          <Button
            type="text"
            size="small"
            icon={<Plus size={14} />}
            aria-label={t("workspace.pdfZoomIn", "Zoom in")}
            disabled={zoom >= MAX_ZOOM || bootLoading}
            onClick={() => bumpZoom(zoom + ZOOM_STEP)}
          />
          <Button
            type="text"
            size="small"
            icon={<RotateCcw size={14} />}
            aria-label={t("workspace.pdfZoomReset", "Reset zoom")}
            disabled={zoom === 1 || bootLoading}
            onClick={() => {
              setFitMode("manual");
              setZoom(1);
            }}
          />
          <span className={styles.pdfFitSeg} role="group">
            <Tooltip title={t("workspace.pdfFitWidth", "Fit width")}>
              <Button
                type="text"
                size="small"
                className={
                  fitMode === "width" ? styles.pdfFitActive : undefined
                }
                icon={<Scan size={14} />}
                aria-label={t("workspace.pdfFitWidth", "Fit width")}
                aria-pressed={fitMode === "width"}
                disabled={bootLoading}
                onClick={() => {
                  setFitMode("width");
                  applyFitZoom("width");
                }}
              />
            </Tooltip>
            <Tooltip title={t("workspace.pdfFitPage", "Fit page")}>
              <Button
                type="text"
                size="small"
                className={fitMode === "page" ? styles.pdfFitActive : undefined}
                icon={<Maximize2 size={14} />}
                aria-label={t("workspace.pdfFitPage", "Fit page")}
                aria-pressed={fitMode === "page"}
                disabled={bootLoading}
                onClick={() => {
                  setFitMode("page");
                  applyFitZoom("page");
                }}
              />
            </Tooltip>
          </span>
        </div>
        {numPages > 0 ? (
          <span className={styles.pdfMeta}>
            {t("workspace.pdfPageCount", "{{count}} pages", {
              count: numPages,
            })}
          </span>
        ) : (
          /* pdf.js is still parsing the fetched bytes. */
          <PdfLoadingBar />
        )}
      </div>
      <div className={styles.pdfBody}>
        {bootOverlayMounted ? (
          <div
            className={
              bootOverlayFading
                ? `${styles.pdfBootOverlay} ${styles.pdfBootOverlayFading}`
                : styles.pdfBootOverlay
            }
            aria-hidden={bootOverlayFading || !bootLoading}
          >
            <DocumentPreviewLoading
              phase={docReady ? "render" : "parse"}
              fill
            />
          </div>
        ) : null}
        {outlineOpen && outline && outline.length > 0 && !isMobile ? (
          <nav
            className={styles.pdfOutlinePanel}
            aria-label={t("workspace.pdfOutline", "Outline")}
          >
            {renderOutline(outline, 0)}
          </nav>
        ) : null}
        {isMobile ? (
          <Drawer
            title={t("workspace.pdfOutline", "Outline")}
            placement="left"
            open={Boolean(outlineOpen && outline && outline.length > 0)}
            onClose={() => setOutlineOpen(false)}
            width={280}
            destroyOnHidden
          >
            {outline && outline.length > 0 ? renderOutline(outline, 0) : null}
          </Drawer>
        ) : null}
        <div className={styles.pdfScroll} ref={scrollRef}>
          {loadFailed ? (
            <div className={styles.pdfEmpty}>
              <span>
                {t("workspace.mediaLoadFailed", "Could not load preview")}
              </span>
              <Button size="small" onClick={handleRetry}>
                {t("workspace.retryPreview", "Retry")}
              </Button>
            </div>
          ) : (
            <Document
              key={reloadKey}
              file={fileUrl}
              loading={null}
              onLoadSuccess={handleLoadSuccess}
              onLoadError={() => {
                setLoadFailed(true);
                setNumPages(0);
                setDocReady(false);
                setFirstPageReady(false);
              }}
              className={styles.pdfDocument}
            >
              {Array.from({ length: numPages }, (_, index) => {
                const pageNo = index + 1;
                const pageHeight = Math.max(
                  120,
                  Math.round(renderWidth * ratioFor(pageNo)),
                );
                const isVisible = visiblePages.has(pageNo);
                return (
                  <div
                    key={`${filename}-${pageNo}`}
                    data-pdf-page={pageNo}
                    className={styles.pdfPageSlot}
                    style={{ width: renderWidth, height: pageHeight }}
                  >
                    {isVisible || !supportsIntersectionObserver ? (
                      <Page
                        pageNumber={pageNo}
                        width={renderWidth}
                        className={styles.pdfPage}
                        renderTextLayer
                        renderAnnotationLayer
                        loading={<PdfPageSkeletonBlock />}
                        onRenderSuccess={() => {
                          if (pageNo === 1) setFirstPageReady(true);
                        }}
                        onRenderError={() => {
                          if (pageNo === 1) setFirstPageReady(true);
                        }}
                      />
                    ) : (
                      <PdfPageSkeletonBlock />
                    )}
                  </div>
                );
              })}
            </Document>
          )}
        </div>
      </div>
    </div>
  );
}
