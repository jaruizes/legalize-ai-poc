export interface Citation {
  source: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  loading?: boolean;
  error?: boolean;
  showCitations?: boolean;
}

export interface BedrockModel {
  label: string;
  id: string;
}

export interface AskFilters {
  ring?: string;
  quadrant?: string;
  editions?: string[];
}

export interface AskRequest {
  question: string;
  session_id?: string;
  model_id?: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  num_results?: number;
  filters?: AskFilters;
  system_prompt?: string;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  session_id: string;
}

export interface InterviewTurn {
  turn_num: number;
  question: string;
  answer: string;
  timestamp: string;
}

export interface Interview {
  session_id: string;
  summary: string;
  turn_count: number;
  created_at: string;
  updated_at: string;
  turns: InterviewTurn[];
}

export interface InterviewSummary {
  session_id: string;
  executive_summary: string;
  turn_count: number;
}
