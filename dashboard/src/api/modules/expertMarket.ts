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

export interface ExpertHubListResponse {
  items: MarketExpert[];
  scenes: string[];
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
    welcome_enrichment: "pending" | "skipped" | "succeeded" | "failed" | string;
  };
  bootstrap_pending: boolean;
}

export interface CreateMarketExpertBody {
  name?: string;
  description?: string;
  providers?: string[];
  default_model?: string;
  backend?: Record<string, unknown>;
}

function hubListPath(query: string, scene: string): string {
  const params = new URLSearchParams();
  const q = query.trim();
  const s = scene.trim();
  if (q) params.set("q", q);
  if (s) params.set("scene", s);
  const qs = params.toString();
  return qs ? `/experts/hub?${qs}` : "/experts/hub";
}

export const expertMarketApi = {
  list: (query: string, scene = "") =>
    request<ExpertHubListResponse>(hubListPath(query, scene)),

  get: (slug: string) =>
    request<MarketExpert>(`/experts/hub/${encodeURIComponent(slug)}`),

  install: (slug: string, body: CreateMarketExpertBody = {}) =>
    request<CreateMarketExpertResponse>(
      `/experts/hub/${encodeURIComponent(slug)}/install`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
};
