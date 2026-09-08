import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { agentChatApi } from "../../../api/modules/agentChat";
import type { OctopAgent } from "../../../context/AgentContext";
import { pickLocale, type LocalizedText } from "../../../utils/localizedText";
import type { WelcomeQuickCard } from "../components/WelcomeScreen";
import { resolveWelcomeSuffix } from "../utils/resolveWelcomeSuffix";

interface WelcomePromptDto {
  title: LocalizedText;
  description: LocalizedText;
  prompt: LocalizedText;
  color?: string;
  icon_name?: string | null;
}

function mapQuickPrompts(
  prompts: WelcomePromptDto[] | undefined,
  locale: "zh" | "en",
): WelcomeQuickCard[] {
  return (prompts ?? []).map((p) => ({
    title: pickLocale(p.title, locale),
    description: pickLocale(p.description, locale),
    prompt: pickLocale(p.prompt, locale),
    color: p.color || "#e8f4ff",
    icon_name: p.icon_name ?? null,
  }));
}

export function useExpertChatWelcome(agent: OctopAgent | null): {
  quickCards: WelcomeQuickCard[];
  welcomeSuffix: string | null;
} {
  const { i18n } = useTranslation();
  const [quickCards, setQuickCards] = useState<WelcomeQuickCard[]>([]);
  const [apiWelcomeSuffix, setApiWelcomeSuffix] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const locale: "zh" | "en" = i18n.language.startsWith("zh") ? "zh" : "en";
    const agentId = agent?.agent_id;
    if (!agentId) {
      setQuickCards([]);
      setApiWelcomeSuffix(null);
      return;
    }

    void agentChatApi
      .welcome(agentId)
      .then((data) => {
        if (cancelled) return;
        setQuickCards(mapQuickPrompts(data.quick_prompts, locale));
        setApiWelcomeSuffix(
          pickLocale(data.welcome_message, locale, { crossFallback: false }) ||
            null,
        );
      })
      .catch(() => {
        if (!cancelled) {
          setQuickCards([]);
          setApiWelcomeSuffix(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [agent?.agent_id, i18n.language]);

  const welcomeSuffix = resolveWelcomeSuffix(
    agent?.description,
    apiWelcomeSuffix,
  );

  return { quickCards, welcomeSuffix };
}
