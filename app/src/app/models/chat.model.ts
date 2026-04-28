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
}
