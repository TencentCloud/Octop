import { useState } from "react";
import { ChevronLeft, ChevronRight, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ExpertIcon } from "../pages/Experts/components/iconForName";
import type { WelcomeQuickCard } from "../pages/Chat/components/WelcomeScreen";

export default function Recommendations({
  cards,
  onPromptClick,
}: {
  cards: WelcomeQuickCard[];
  onPromptClick: (text: string, options?: { prefill?: boolean }) => void;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(0);
  const pages = Math.ceil(cards.length / 4);
  const current = Math.min(page, Math.max(0, pages - 1));
  return (
    <section
      className="wb-related-playbooks"
      aria-label={t("workbuddy.recommendedTasks")}
    >
      <header className="wb-related-playbooks__header">
        <h2 className="wb-related-playbooks__title">
          <Sparkles size={16} />
          {t("workbuddy.recommendedTasks")}
        </h2>
        {pages > 1 && (
          <div className="wb-related-playbooks__header-actions">
            <button
              type="button"
              className="wb-related-playbooks__pager"
              aria-label={t("workbuddy.previousRecommendations")}
              disabled={current === 0}
              onClick={() => setPage(current - 1)}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              className="wb-related-playbooks__pager"
              aria-label={t("workbuddy.nextRecommendations")}
              disabled={current === pages - 1}
              onClick={() => setPage(current + 1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </header>
      <div className="wb-related-playbooks__row">
        {cards.slice(current * 4, current * 4 + 4).map((card, index) => (
          <button
            className="wb-related-playbooks__card"
            type="button"
            key={`${index}:${card.title}`}
            title={card.description}
            onClick={() => onPromptClick(card.prompt, { prefill: true })}
          >
            <span className="wb-related-playbooks__card-cover wb-recommendation-cover">
              <ExpertIcon
                iconUrl={card.icon_url}
                iconName={card.icon_name}
                size={24}
              />
              <span>{card.description}</span>
              {card.expertName && <small>@{card.expertName}</small>}
            </span>
            <span className="wb-related-playbooks__card-title">
              {card.title}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
