export interface UserQuestionOption {
  label: string;
  description?: string;
}

export interface UserQuestion {
  id: string;
  question: string;
  header?: string;
  options: UserQuestionOption[];
  multi_select?: boolean;
}

export interface UserQuestionAnswer {
  id: string;
  selected: string[];
  custom?: string;
}

export interface UserQuestionPendingPayload {
  pending_id: string;
  questions: UserQuestion[];
}
