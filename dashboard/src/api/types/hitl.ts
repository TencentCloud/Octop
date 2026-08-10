export interface HitlActionRequest {
  name: string;
  args?: Record<string, unknown>;
  description?: string;
}

export interface HitlReviewConfig {
  action_name: string;
  allowed_decisions: string[];
}

export interface HitlPendingPayload {
  pending_id?: string;
  action_requests: HitlActionRequest[];
  review_configs?: HitlReviewConfig[];
}
