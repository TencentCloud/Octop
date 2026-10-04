import Recommendations from "./Recommendations";
import { WORKBUDDY_UI } from "./variant";
import { useEffect, useRef, type ReactNode } from "react";
import type { WelcomeQuickCard } from "../pages/Chat/components/WelcomeScreen";

/** The composer stays in this tree when the welcome screen becomes a conversation. */
export default function ConversationLayout({
  welcome,
  children,
  cards,
  onPromptClick,
}: {
  welcome: boolean;
  children: ReactNode;
  cards: WelcomeQuickCard[];
  onPromptClick: (text: string, options?: { prefill?: boolean }) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const slot = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!welcome || !slot.current || !host.current) return;
    const element = host.current;
    const content = element.querySelector(".wb-composer");
    const footer = slot.current;
    if (!content) return;
    const position = () => {
      const bottom =
        element.getBoundingClientRect().bottom -
        content.getBoundingClientRect().bottom -
        footer.offsetHeight -
        24;
      footer.style.bottom = `${Math.floor(Math.min(56, bottom))}px`;
    };
    position();
    const observer = new ResizeObserver(position);
    observer.observe(element);
    observer.observe(content);
    observer.observe(footer);
    return () => observer.disconnect();
  }, [welcome, cards.length]);
  if (!WORKBUDDY_UI) return <>{children}</>;
  return (
    <div
      ref={host}
      className={`wb-conversation-body${welcome ? " wb-home-page" : ""}`}
    >
      <div
        className={
          welcome
            ? "wb-home-page__main-content"
            : "wb-conversation-body__content"
        }
      >
        {children}
      </div>
      {welcome && cards.length > 0 && (
        <div ref={slot} className="wb-home-page__related-playbooks-slot">
          <Recommendations cards={cards} onPromptClick={onPromptClick} />
        </div>
      )}
    </div>
  );
}
