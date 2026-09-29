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

  // DOMMatrix —— ``react-pdf`` / ``pdfjs`` 在 jsdom 下缺这个全局。
  //
  // ★ 统一补（批次十四 `T-B-SETUP`）：此前是**各测试文件各自** ``vi.mock("react-pdf")``
  //   绕过（`AssetsTab.test.tsx` / `ProjectsPage.test.tsx`），本卡改为**一处补齐**，
  //   并删除局部绕过 —— 局部绕过会让"该模块从未真正加载"变成常态，
  //   从而**静默**掩盖真实的模块加载期缺陷。
  //
  // ★ 开关：``OCTOP_TEST_NO_DOMMATRIX=1`` ⇒ **故意不补**，供 `T-B-LAZY` 的
  //   「判据自足」（不依赖本卡先后顺序）使用：那条用例自己显式去掉 polyfill。
  // ★ 只补到"能加载/能构造"为止（**不为让 PDF 真渲染而补** —— 见卡面 contract）。
  if (
    process.env.OCTOP_TEST_NO_DOMMATRIX !== "1" &&
    typeof globalThis.DOMMatrix === "undefined"
  ) {
    class _DOMMatrix {
      a = 1;
      b = 0;
      c = 0;
      d = 1;
      e = 0;
      f = 0;
      constructor(init?: number[] | _DOMMatrix) {
        if (Array.isArray(init) && init.length >= 6) {
          [this.a, this.b, this.c, this.d, this.e, this.f] = init;
        } else if (init instanceof _DOMMatrix) {
          this.a = init.a;
          this.b = init.b;
          this.c = init.c;
          this.d = init.d;
          this.e = init.e;
          this.f = init.f;
        }
      }
      static fromMatrix(other?: _DOMMatrix) {
        return new _DOMMatrix(other ?? undefined);
      }
      static fromFloat32Array(values: Float32Array) {
        return new _DOMMatrix(Array.from(values));
      }
      static fromFloat64Array(values: Float64Array) {
        return new _DOMMatrix(Array.from(values));
      }
      multiply(other: _DOMMatrix) {
        return new _DOMMatrix([
          this.a * other.a + this.c * other.b,
          this.b * other.a + this.d * other.b,
          this.a * other.c + this.c * other.d,
          this.b * other.c + this.d * other.d,
          this.a * other.e + this.c * other.f + this.e,
          this.b * other.e + this.d * other.f + this.f,
        ]);
      }
      translate(x = 0, y = 0) {
        return this.multiply(new _DOMMatrix([1, 0, 0, 1, x, y]));
      }
      scale(value = 1) {
        return this.multiply(new _DOMMatrix([value, 0, 0, value, 0, 0]));
      }
      inverse() {
        const det = this.a * this.d - this.b * this.c || 1;
        return new _DOMMatrix([
          this.d / det,
          -this.b / det,
          -this.c / det,
          this.a / det,
          (this.c * this.f - this.d * this.e) / det,
          (this.b * this.e - this.a * this.f) / det,
        ]);
      }
      get isIdentity() {
        return (
          this.a === 1 &&
          this.b === 0 &&
          this.c === 0 &&
          this.d === 1 &&
          this.e === 0 &&
          this.f === 0
        );
      }
      toString() {
        return `matrix(${this.a}, ${this.b}, ${this.c}, ${this.d}, ${this.e}, ${this.f})`;
      }
    }
    (globalThis as unknown as { DOMMatrix: typeof _DOMMatrix }).DOMMatrix =
      _DOMMatrix;
  }

  // ``Promise.withResolvers`` —— pdfjs（react-pdf 传递依赖）在**模块加载期**就会用到，
  // 本仓 Node 版本下缺失 ⇒ 未补时整个 pdf 边加载即抛
  // （实测：`TypeError: Promise.withResolvers is not a function`）。
  // ★ 与 DOMMatrix 同一个开关：``OCTOP_TEST_NO_DOMMATRIX=1`` ⇒ 一并**不补**
  //   （`T-B-LAZY` 的判据自足用例据此证明"该边在模块加载期不存在"）。
  if (
    process.env.OCTOP_TEST_NO_DOMMATRIX !== "1" &&
    typeof (Promise as unknown as { withResolvers?: unknown }).withResolvers !==
      "function"
  ) {
    (
      Promise as unknown as {
        withResolvers: <T>() => {
          promise: Promise<T>;
          resolve: (value: T | PromiseLike<T>) => void;
          reject: (reason?: unknown) => void;
        };
      }
    ).withResolvers = <T>() => {
      let resolve!: (value: T | PromiseLike<T>) => void;
      let reject!: (reason?: unknown) => void;
      const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
      });
      return { promise, resolve, reject };
    };
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
