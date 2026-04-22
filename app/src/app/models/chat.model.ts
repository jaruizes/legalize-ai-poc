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

export interface AskRequest {
  question: string;
  temperature?: number;
  max_tokens?: number;
  top_p?: number;
  num_results?: number;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
}
