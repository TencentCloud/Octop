import { useState } from "react";
import { useTranslation } from "react-i18next";
import SceneTabs, { type WelcomeScene } from "./SceneTabs";
import type { WelcomeQuickCard } from "../pages/Chat/components/WelcomeScreen";
import SourceSceneIcon from "./SourceSceneIcon";

export interface WorkBuddyWelcomeProps {
  onPromptClick: (text: string, options?: { prefill?: boolean }) => void;
  agentName?: string | null;
  welcomeSuffix?: string | null;
  quickCards: WelcomeQuickCard[];
  isTeam?: boolean;
}

export default function WorkBuddyWelcome({
  onPromptClick,
  agentName,
  welcomeSuffix,
  isTeam,
}: WorkBuddyWelcomeProps) {
  const { t } = useTranslation();
  const [scene, setScene] = useState<WelcomeScene>("work");
  // Scene selection only changes prompt suggestions; conversation_mode stays in Octop.
  const suggestions = t(`workbuddy.suggestions.${scene}`, {
    returnObjects: true,
  }) as string[];
  return (
    <div className="wb-welcome wb-home-page__welcome">
      <header className="wb-home-header">
        <div className="wb-home-header__title-wrap">
          <h1 className="wb-home-header__title">
            {isTeam
              ? t("chatWelcome.teamHeading", { name: agentName })
              : t("workbuddy.greeting")}
          </h1>
          {welcomeSuffix && (
            <p className="wb-home-header__slogan">{welcomeSuffix}</p>
          )}
        </div>
      </header>
      <SceneTabs value={scene} onChange={setScene} />
      <div
        className="quick-actions-container wb-home-composer__chips"
        aria-label={t("workbuddy.suggestionsLabel")}
      >
        <div className="quick-actions">
          <div className="quick-actions__list">
            {suggestions.map((prompt) => (
              <button
                key={prompt}
                type="button"
                className="quick-actions__item"
                onClick={() => onPromptClick(prompt, { prefill: true })}
              >
                <SourceSceneIcon scene={scene} />
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
