import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../hooks/useChat";
import { groupConsecutiveAssistantMessages } from "../utils/messageGrouping";
import TurnTimelineRail from "./TurnTimelineRail";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      if (key === "chat.turnTimeline.jumpToQuery") {
        return `Jump ${opts?.index ?? ""}`.trim();
      }
      return key;
    },
  }),
}));

function msg(
  role: ChatMessage["role"],
  id: string,
  content: string,
): ChatMessage {
  return {
    id,
    role,
    content,
    status: "done",
    timestamp: Date.now(),
  };
}

function mountScrollerWithAnchors(ids: string[]) {
  const scroller = document.createElement("div");
  Object.defineProperty(scroller, "clientHeight", {
    configurable: true,
    value: 600,
  });
  Object.defineProperty(scroller, "scrollTop", {
    configurable: true,
    writable: true,
    value: 0,
  });
  scroller.getBoundingClientRect = () =>
    ({
      top: 0,
      left: 0,
      bottom: 600,
      right: 400,
      width: 400,
      height: 600,
      x: 0,
      y: 0,
      toJSON() {
        return {};
      },
    }) as DOMRect;

  const bubbleRefsMap = new Map<string, HTMLDivElement>();
  ids.forEach((id, index) => {
    const el = document.createElement("div");
    el.dataset.messageId = id;
    el.dataset.role = "user";
    el.className = "userBubble messageBubble";
    el.getBoundingClientRect = () =>
      ({
        top: 40 + index * 200,
        left: 80,
        bottom: 140 + index * 200,
        right: 360,
        width: 280,
        height: 100,
        x: 80,
        y: 40 + index * 200,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    scroller.appendChild(el);
    bubbleRefsMap.set(id, el);
  });
  document.body.appendChild(scroller);
  return { scroller, bubbleRefsMap };
}

describe("TurnTimelineRail", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "MutationObserver",
      class {
        observe() {}
        disconnect() {}
        takeRecords() {
          return [];
        }
      },
    );
    vi.stubGlobal(
      "ResizeObserver",
      class {
        callback: ResizeObserverCallback;
        constructor(cb: ResizeObserverCallback) {
          this.callback = cb;
        }
        observe(target: Element) {
          this.callback(
            [
              {
                target,
                contentRect: {
                  width: 960,
                  height: 700,
                } as DOMRectReadOnly,
                borderBoxSize: [],
                contentBoxSize: [],
                devicePixelContentBoxSize: [],
              } as ResizeObserverEntry,
            ],
            this as unknown as ResizeObserver,
          );
        }
        unobserve() {}
        disconnect() {}
      },
    );
  });

  afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
    vi.unstubAllGlobals();
  });

  it("renders ticks for two user turns and jumps on click", async () => {
    const messages = [
      msg("user", "u1", "first question"),
      msg("assistant", "a1", "first answer"),
      msg("user", "u2", "second question"),
      msg("assistant", "a2", "second answer"),
    ];
    const messageGroups = groupConsecutiveAssistantMessages(messages);
    const { scroller, bubbleRefsMap } = mountScrollerWithAnchors(["u1", "u2"]);
    const scrollerRef = { current: null as HTMLElement | null };
    const containerRef = { current: scroller as HTMLDivElement | null };
    const virtuosoRef = { current: null };
    const wrapper = document.createElement("div");
    Object.defineProperty(wrapper, "clientWidth", {
      configurable: true,
      value: 960,
    });
    document.body.appendChild(wrapper);
    const wrapperRef = { current: wrapper };
    const armProgrammaticGuard = vi.fn();
    const scrollTo = vi.fn();
    scroller.scrollTo = scrollTo;

    render(
      <TurnTimelineRail
        messages={messages}
        messageGroups={messageGroups}
        following={false}
        useVirtual={false}
        firstItemIndex={0}
        scrollerRef={scrollerRef}
        containerRef={containerRef}
        virtuosoRef={virtuosoRef}
        bubbleRefsMap={{ current: bubbleRefsMap }}
        wrapperRef={wrapperRef}
        armProgrammaticGuard={armProgrammaticGuard}
      />,
    );

    const rail = await screen.findByTestId("turn-timeline-rail");
    expect(rail).toHaveAttribute("data-item-count", "2");
    expect(rail).toHaveAttribute("data-visible", "true");
    expect(rail).toHaveAttribute("data-direction", "ltr");

    fireEvent.click(screen.getByTestId("turn-timeline-tick-0"));
    await waitFor(() => {
      expect(armProgrammaticGuard).toHaveBeenCalled();
    });
    expect(scrollTo).toHaveBeenCalled();
  });

  it("marks rtl direction for preview placement", async () => {
    document.documentElement.setAttribute("dir", "rtl");
    const messages = [
      msg("user", "u1", "first"),
      msg("assistant", "a1", "a"),
      msg("user", "u2", "second"),
      msg("assistant", "a2", "b"),
    ];
    const messageGroups = groupConsecutiveAssistantMessages(messages);
    const { scroller, bubbleRefsMap } = mountScrollerWithAnchors(["u1", "u2"]);
    const wrapper = document.createElement("div");
    Object.defineProperty(wrapper, "clientWidth", {
      configurable: true,
      value: 960,
    });
    document.body.appendChild(wrapper);

    render(
      <TurnTimelineRail
        messages={messages}
        messageGroups={messageGroups}
        useVirtual={false}
        firstItemIndex={0}
        scrollerRef={{ current: null }}
        containerRef={{ current: scroller }}
        virtuosoRef={{ current: null }}
        bubbleRefsMap={{ current: bubbleRefsMap }}
        wrapperRef={{ current: wrapper }}
        armProgrammaticGuard={vi.fn()}
      />,
    );

    const rail = await screen.findByTestId("turn-timeline-rail");
    expect(rail).toHaveAttribute("data-direction", "rtl");
    document.documentElement.setAttribute("dir", "ltr");
  });

  it("hides when fewer than two user turns", () => {
    const messages = [
      msg("user", "u1", "only one"),
      msg("assistant", "a1", "reply"),
    ];
    const messageGroups = groupConsecutiveAssistantMessages(messages);
    const { scroller, bubbleRefsMap } = mountScrollerWithAnchors(["u1"]);
    const wrapper = document.createElement("div");
    Object.defineProperty(wrapper, "clientWidth", {
      configurable: true,
      value: 960,
    });
    document.body.appendChild(wrapper);

    const { container } = render(
      <TurnTimelineRail
        messages={messages}
        messageGroups={messageGroups}
        useVirtual={false}
        firstItemIndex={0}
        scrollerRef={{ current: null }}
        containerRef={{ current: scroller }}
        virtuosoRef={{ current: null }}
        bubbleRefsMap={{ current: bubbleRefsMap }}
        wrapperRef={{ current: wrapper }}
        armProgrammaticGuard={vi.fn()}
      />,
    );

    expect(
      container.querySelector('[data-testid="turn-timeline-rail"]'),
    ).toBeNull();
  });
});
