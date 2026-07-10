import { request } from "../request";

export interface LocalizedText {
  zh?: string;
  en?: string;
}

export interface ExpertMarketQuickPrompt {
  title: LocalizedText;
  description: LocalizedText;
  prompt: LocalizedText;
  color?: string;
  icon_name?: string | null;
}

export interface MarketExpert {
  id: string;
  slug: string;
  label: LocalizedText;
  description: LocalizedText;
  scene?: string;
  sub_scene?: string;
  icon_url?: string | null;
  icon_name?: string | null;
  color?: string | null;
  skill_slugs?: string[];
  skill_count?: number;
  source?: string;
  content?: LocalizedText;
  quick_prompts?: ExpertMarketQuickPrompt[];
}

export interface CreateMarketExpertResponse {
  id: number | string;
  agent_id: string;
  user_id: number;
  name: string;
  description?: string | null;
  default_model?: string | null;
  state: string;
  expert_id: string;
  icon_name?: string | null;
  color?: string | null;
  market: {
    source: string;
    kind: string;
    slug: string;
    quick_prompts_generated: boolean;
  };
  bootstrap_pending: boolean;
}

export const expertMarketApi = {
  listSkillsets: (query: string) =>
    request<MarketExpert[]>(
      `/experts/hub/skillsets?q=${encodeURIComponent(query.trim())}`,
    ),

  getSkillset: (slug: string) =>
    request<MarketExpert>(
      `/experts/hub/skillsets/${encodeURIComponent(slug)}`,
    ),

  createFromSkillset: (slug: string) =>
    request<CreateMarketExpertResponse>(
      `/agents/from-expert-market/skillsets/${encodeURIComponent(slug)}`,
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    ),
};
