export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  mime_type: string | null;
  size_bytes: number;
  sha256: string;
  status: DocumentStatus;
  error_message: string | null;
  progress: number;
  page_count: number | null;
  char_count: number | null;
  chunk_count: number;
  chunk_size: number | null;
  chunk_overlap: number | null;
  embedding_model: string | null;
  processing_ms: number | null;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
}

export interface DocumentList {
  items: DocumentItem[];
  total: number;
}

export interface UploadResult {
  filename: string;
  status: "accepted" | "duplicate" | "rejected";
  document: DocumentItem | null;
  error: string | null;
}

export interface UploadResponse {
  results: UploadResult[];
  accepted: number;
  duplicates: number;
  rejected: number;
}

export interface ChunkItem {
  id: string;
  text: string;
  metadata: Record<string, string | number | boolean>;
}

export interface ChunkList {
  items: ChunkItem[];
  document_id: string;
  total: number;
}

export interface Source {
  index: number;
  document_id: string;
  filename: string;
  file_type: string | null;
  page: number | null;
  section: string | null;
  chunk_index: number | null;
  similarity: number;
  snippet: string;
  cited: boolean;
  /** The model gave no [n] markers; attribution was derived from word overlap. */
  inferred?: boolean;
}

export type AnswerType = "grounded" | "insufficient" | "no_context" | "small_talk" | "error";

export interface MessageMeta {
  answer_type?: AnswerType;
  model?: string | null;
  latency_ms?: number;
  interrupted?: boolean;
  error?: string;
  similarity_threshold?: number;
  retrieval?: {
    best_similarity: number | null;
    candidates: number;
    rejected_below_threshold: number;
    used: number;
  };
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  meta: MessageMeta;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

export interface RuntimeSettings {
  llm_model: string;
  llm_temperature: number;
  chunk_size: number;
  chunk_overlap: number;
  retrieval_top_k: number;
  similarity_threshold: number;
  relative_score_cutoff: number;
  max_context_chars: number;
  history_turns: number;
}

export interface SystemInfo {
  app_name: string;
  environment: string;
  embedding_model: string;
  embedding_batch_size: number;
  ollama_base_url: string;
  ollama_num_ctx: number;
  max_upload_mb: number;
  max_files_per_upload: number;
  supported_types: string[];
  auth_enabled: boolean;
  database_backend: string;
}

export interface SettingsResponse {
  settings: RuntimeSettings;
  defaults: RuntimeSettings;
  system: SystemInfo;
  stale_documents: number;
}

export interface OllamaModel {
  name: string;
  size_bytes: number | null;
  parameter_size: string | null;
  quantization: string | null;
  family: string | null;
  modified_at: string | null;
}

export interface ModelsResponse {
  available: boolean;
  models: OllamaModel[];
  current: string;
  error: string | null;
}

export type HealthStatus = "ok" | "degraded" | "error";

export interface ComponentHealth {
  status: HealthStatus;
  detail: string | null;
  info: Record<string, unknown>;
}

export interface ReadinessResponse {
  status: HealthStatus;
  components: Record<string, ComponentHealth>;
}

export interface StatsResponse {
  documents_total: number;
  documents_by_status: Partial<Record<DocumentStatus, number>>;
  documents_by_type: Record<string, number>;
  total_chunks: number;
  vector_count: number;
  total_size_bytes: number;
  conversations: number;
  messages: number;
  questions_answered: number;
  answers_by_type: Partial<Record<AnswerType | "unknown", number>>;
  avg_latency_ms: number | null;
  processing_queue: number;
  recent_documents: Array<Pick<DocumentItem, "id" | "filename" | "file_type" | "status" | "chunk_count" | "created_at">>;
}
