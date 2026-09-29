/**
 * Vitest jsdom setup.
 *
 * Antd's components rely on a few browser APIs jsdom doesn't ship:
 *   - ``window.matchMedia`` (used by Grid responsive breakpoints)
 *   - ``ResizeObserver`` (used by Card/Drawer/Modal portals)
 *   - ``IntersectionObserver`` (used by virtual lists)
 *
 * Recharts also wants ``ResizeObserver`` for the ``ResponsiveContainer``;
 * it'll log a console error otherwise even though our snapshot tests
 * don't actually render the chart at a real size.
 */

import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// Auto-mock react-i18next so components' ``t(key, fallback)`` calls
// resolve synchronously to ``fallback`` without needing the real
// i18n module (which would async-fetch tool labels and add 1-2s of
// console noise per test file).
vi.mock("react-i18next", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-i18next")>();

  type TOptions = Record<string, unknown> & { defaultValue?: string };

  // Interpolate ``{{name}}`` placeholders like real i18next so tests can
  // assert user-visible copy such as "已捕获 42 条对话记忆".
  const interpolate = (template: string, options?: TOptions): string => {
    if (!options) return template;
    return template.replace(/\{\{(\w+)\}\}/g, (match, name: string) =>
      name in options ? String(options[name]) : match,
    );
  };

  return {
    ...actual,
    useTranslation: () => ({
      t: (
        key: string,
        fallback?: string | TOptions,
        options?: TOptions,
      ): string => {
        if (typeof fallback === "string") return interpolate(fallback, options);
        if (fallback && typeof fallback === "object") {
          const template = fallback.defaultValue ?? key;
          return interpolate(template, fallback);
        }
        return key;
      },
      i18n: { language: "zh", changeLanguage: () => Promise.resolve() },
    }),
    Trans: ({ children }: { children?: React.ReactNode }) => children,
  };
});

afterEach(() => {
  cleanup();
});

if (typeof window !== "undefined") {
  // matchMedia
  if (!window.matchMedia) {
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  }

  // ResizeObserver
  class _ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  if (!window.ResizeObserver) {
    (
      window as unknown as { ResizeObserver: typeof _ResizeObserver }
    ).ResizeObserver = _ResizeObserver;
  }

  // IntersectionObserver
  class _IntersectionObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
    root = null;
    rootMargin = "";
    thresholds = [];
  }
  if (!window.IntersectionObserver) {
    (
      window as unknown as {
        IntersectionObserver: typeof _IntersectionObserver;
      }
    ).IntersectionObserver = _IntersectionObserver;
  }

  // jsdom ships no ``DOMMatrix``, but pdfjs-dist instantiates one at module
  // load (``const SCALE_MATRIX = new DOMMatrix()``) — so importing the PDF
  // preview chain threw ``ReferenceError: DOMMatrix is not defined`` and
  // failed the whole suite before a single test ran. Minimal 2D subset
  // covering exactly what pdfjs touches: the identity / 6-element
  // constructor, the writable ``a``-``f`` fields, and the five 2D methods it
  // calls. Semantics follow the DOM spec; the guard below leaves a native
  // ``DOMMatrix`` (real browser, newer jsdom) untouched.
  type Matrix2D = {
    a: number;
    b: number;
    c: number;
    d: number;
    e: number;
    f: number;
  };

  // Row-vector product ``m1 × m2`` — the convention the DOM spec uses for
  // ``multiplySelf`` / ``preMultiplySelf``.
  const multiply2D = (m1: Matrix2D, m2: Matrix2D): number[] => [
    m1.a * m2.a + m1.b * m2.c,
    m1.a * m2.b + m1.b * m2.d,
    m1.c * m2.a + m1.d * m2.c,
    m1.c * m2.b + m1.d * m2.d,
    m1.e * m2.a + m1.f * m2.c + m2.e,
    m1.e * m2.b + m1.f * m2.d + m2.f,
  ];

  const set2D = <T extends Matrix2D>(target: T, values: number[]): T => {
    target.a = values[0];
    target.b = values[1];
    target.c = values[2];
    target.d = values[3];
    target.e = values[4];
    target.f = values[5];
    return target;
  };

  class _DOMMatrix implements Matrix2D {
    a = 1;
    b = 0;
    c = 0;
    d = 1;
    e = 0;
    f = 0;

    constructor(init?: ArrayLike<number>) {
      if (init && init.length >= 6) {
        set2D(this, [init[0], init[1], init[2], init[3], init[4], init[5]]);
      }
    }

    multiplySelf(other: Matrix2D): this {
      return set2D(this, multiply2D(this, other));
    }

    preMultiplySelf(other: Matrix2D): this {
      return set2D(this, multiply2D(other, this));
    }

    translate(tx = 0, ty = 0): _DOMMatrix {
      return new _DOMMatrix(
        multiply2D(this, { a: 1, b: 0, c: 0, d: 1, e: tx, f: ty }),
      );
    }

    scale(sx = 1, sy = sx): _DOMMatrix {
      return new _DOMMatrix(
        multiply2D(this, { a: sx, b: 0, c: 0, d: sy, e: 0, f: 0 }),
      );
    }

    invertSelf(): this {
      const det = this.a * this.d - this.b * this.c;
      if (!Number.isFinite(det) || det === 0) {
        // The DOM spec leaves a non-invertible matrix as all-NaN rather than
        // throwing; match that so pdfjs's own guards see the same input.
        return set2D(this, [NaN, NaN, NaN, NaN, NaN, NaN]);
      }
      return set2D(this, [
        this.d / det,
        -this.b / det,
        -this.c / det,
        this.a / det,
        (this.c * this.f - this.d * this.e) / det,
        (this.b * this.e - this.a * this.f) / det,
      ]);
    }
  }

  if (!("DOMMatrix" in globalThis)) {
    (globalThis as unknown as { DOMMatrix: typeof _DOMMatrix }).DOMMatrix =
      _DOMMatrix;
  }

  // jsdom doesn't implement ``getComputedStyle().transition`` properly,
  // so antd's wave / motion can throw — silence that one noisy console
  // warning without hiding real errors.
  const _origError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    const first = args[0];
    if (
      typeof first === "string" &&
      (first.includes(
        "Not implemented: HTMLFormElement.prototype.requestSubmit",
      ) ||
        first.includes("React does not recognize the") ||
        first.includes("antd: ") ||
        first.includes("[antd:"))
    ) {
      return;
    }
    _origError(...args);
  };
}
