variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "eu-west-1"
}

variable "project" {
  type        = string
  description = "Project name"
  default     = "radar-ai-poc"
}

variable "environment" {
  type        = string
  description = "Environment"
  default     = "dev"
}

variable "kb_model_id" {
  description = "The ID of the foundational model used by the knowledge base."
  type        = string
  default     = "amazon.titan-embed-text-v2:0"
}

variable "kb_name" {
  description = "The knowledge base name."
  type        = string
  default     = "advanced-rag-kb"
}

variable "vector_dimension" {
  description = "The dimension of the vectors produced by the model."
  type        = number
  default     = 1024
}

variable "chunking_strategy" {
  type        = string
  description = "Chunking strategy to use (DEFAULT, FIXED_SIZE, HIERARCHICAL, SEMANTIC, NONE)"
  default     = "HIERARCHICAL"
  validation {
    condition     = contains(["DEFAULT", "FIXED_SIZE", "HIERARCHICAL", "SEMANTIC", "NONE"], var.chunking_strategy)
    error_message = "Chunking strategy must be one of: DEFAULT, FIXED_SIZE, HIERARCHICAL, SEMANTIC, NONE"
  }
}

# Fixed Size Chunking Variables
variable "fixed_size_max_tokens" {
  type        = number
  description = "Maximum number of tokens for fixed-size chunking"
  default     = 512
}

variable "fixed_size_overlap_percentage" {
  type        = number
  description = "Percentage of overlap between chunks"
  default     = 20
}

# Hierarchical Chunking Variables
variable "hierarchical_overlap_tokens" {
  type        = number
  description = "Number of tokens to overlap in hierarchical chunking"
  default     = 60
}

variable "hierarchical_parent_max_tokens" {
  type        = number
  description = "Maximum tokens for parent chunks — covers several related blips for broad queries"
  default     = 1500
}

variable "hierarchical_child_max_tokens" {
  type        = number
  description = "Maximum tokens for child chunks — sized to capture one blip description"
  default     = 400
}

# Semantic Chunking Variables
variable "semantic_max_tokens" {
  type        = number
  description = "Maximum tokens for semantic chunking"
  default     = 512
}

variable "semantic_buffer_size" {
  type        = number
  description = "Buffer size for semantic chunking"
  default     = 1
}

variable "semantic_breakpoint_percentile_threshold" {
  type        = number
  description = "Breakpoint percentile threshold for semantic chunking"
  default     = 75
}

# API / Lambda variables
variable "inference_profile_id" {
  description = "Bedrock inference profile ID for Lambda IAM permissions"
  type        = string
  default     = "eu.amazon.nova-lite-v1:0"
}

variable "generative_model_id" {
  description = "Bedrock foundation model ID or inference profile ARN/ID used for answer generation"
  type        = string
  default     = "amazon.nova-lite-v1:0"
}

variable "api_system_prompt" {
  description = "System prompt sent to the generative model on every /ask request. This defines the AI assistant's identity and constraints."
  type        = string
  default     = "You are a helpful expert assistant. Answer questions accurately and concisely based on the provided documents. Respond in the same language as the question. Always cite the specific documents and sections you reference."
}

variable "default_max_tokens" {
  description = "Default maximum number of output tokens"
  type        = number
  default     = 2048
}

// Documents data source
variable "datasource_repo_url" {
  type        = string
  description = "URL of the GitHub repository containing the documents"
  default     = "https://github.com/jaruizes/thoughtworks-radar-vols.git"
}

# UI Configuration Variables
variable "ui_title" {
  type        = string
  description = "Application title"
  default     = "Tech Radar Explorer"
}

variable "ui_subtitle" {
  type        = string
  description = "Application subtitle"
  default     = "Analiza la evolución tecnológica y tendencias basadas en los volúmenes del Thoughtworks Technology Radar."
}

variable "ui_icon" {
  type        = string
  description = "Application icon (emoji or text)"
  default     = "🔍"
}

variable "ui_examples" {
  type        = list(string)
  description = "List of example questions"
  default     = [
    "¿Cómo han evolucionado las herramientas asociadas a la IA en los dos últimos años?",
    "¿Qué tecnologías han pasado a la fase de 'Adopt' recientemente?",
    "¿Qué riesgos se mencionan respecto al uso de LLMs en producción?",
    "Analiza la evolución de las plataformas de datos desde 2023."
  ]
}

variable "ui_disclaimer" {
  type        = string
  description = "Disclaimer text for the footer"
  default     = "Tech Radar Explorer utiliza IA para sintetizar información. Verifica siempre los volúmenes originales del Radar de Thoughtworks."
}

variable "guardrail_grounding_threshold" {
  description = "Contextual grounding score threshold (0–1). Answers below this score are blocked. 0.4 is a good default for multi-document synthesis queries."
  type        = number
  default     = 0.4
}

variable "guardrail_relevance_threshold" {
  description = "Relevance score threshold (0–1). Answers below this score are blocked. 0.4 is a good default for multi-document synthesis queries."
  type        = number
  default     = 0.4
}
