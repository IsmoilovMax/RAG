import { SSEParser } from "@/lib/sse";
import type {
  ChatMessage,
  ChunkList,
  ConversationDetail,
  ConversationSummary,
  DocumentItem,
  DocumentList,
  DocumentStatus,
  ModelsResponse,
  ReadinessResponse,
  RuntimeSettings,
  SettingsResponse,
  Source,
  StatsResponse,
  UploadResponse,
} from "@/lib/types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "/api";
const API_KEY_STORAGE = "documind-api-key";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function setApiKey(key: string) {
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE, key);
    else localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    /* storage unavailable */
  }
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const key = getApiKey();
  if (key) h.set("X-API-Key", key);
  return h;
}

async function parseError(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status})`;
  let code: string | undefined;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) {
      message = body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || message;
    }
    code = body.code;
  } catch {
    /* non-JSON error body */
  }
  if (response.status === 401) message = "Unauthorized — set a valid API key in Settings.";
  return new ApiError(message, response.status, code);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers: headers(init.headers) });
  } catch {
    throw new ApiError("Cannot reach the server. Is the backend running?", 0, "network_error");
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json = (body: unknown): RequestInit => ({
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json" },
});

export const api = {
  // system
  health: () => request<{ status: string }>("/health"),
  readiness: async (): Promise<ReadinessResponse> => {
    // 503 still carries a useful body.
    const response = await fetch(`${API_BASE}/health/ready`, { headers: headers() }).catch(() => null);
    if (!response) throw new ApiError("Cannot reach the server", 0, "network_error");
    return (await response.json()) as ReadinessResponse;
  },
  stats: () => request<StatsResponse>("/stats"),

  // documents
  listDocuments: (params: { status?: DocumentStatus; q?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.status) search.set("status", params.status);
    if (params.q) search.set("q", params.q);
    const qs = search.toString();
    return request<DocumentList>(`/documents${qs ? `?${qs}` : ""}`);
  },
  getDocument: (id: string) => request<DocumentItem>(`/documents/${id}`),
  getChunks: (id: string, limit = 100) => request<ChunkList>(`/documents/${id}/chunks?limit=${limit}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  reprocessDocument: (id: string) => request<DocumentItem>(`/documents/${id}/reprocess`, { method: "POST" }),
  reindexAll: () => request<{ queued: number }>("/documents/reindex", { method: "POST" }),
  downloadUrl: (id: string) => `${API_BASE}/documents/${id}/file`,
  downloadDocument: async (doc: DocumentItem) => {
    const response = await fetch(`${API_BASE}/documents/${doc.id}/file`, { headers: headers() });
    if (!response.ok) throw await parseError(response);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement("a"), { href: url, download: doc.filename });
    a.click();
    URL.revokeObjectURL(url);
  },
  uploadDocuments: (files: File[], onProgress?: (fraction: number) => void) =>
    new Promise<UploadResponse>((resolve, reject) => {
      const form = new FormData();
      files.forEach((f) => form.append("files", f, f.name));
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${API_BASE}/documents`);
      const key = getApiKey();
      if (key) xhr.setRequestHeader("X-API-Key", key);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress?.(e.loaded / e.total);
      };
      xhr.onerror = () => reject(new ApiError("Upload failed: network error", 0, "network_error"));
      xhr.onload = () => {
        let body: { detail?: string } & Partial<UploadResponse> = {};
        try {
          body = JSON.parse(xhr.responseText);
        } catch {
          /* ignore */
        }
        if (xhr.status >= 200 && xhr.status < 300) resolve(body as UploadResponse);
        else if (xhr.status === 401) reject(new ApiError("Unauthorized — set a valid API key in Settings.", 401));
        else if (xhr.status === 413) reject(new ApiError(body.detail ?? "Upload too large", 413));
        else reject(new ApiError(body.detail ?? `Upload failed (${xhr.status})`, xhr.status));
      };
      xhr.send(form);
    }),

  // chat
  listConversations: () => request<ConversationSummary[]>("/chat/conversations"),
  getConversation: (id: string) => request<ConversationDetail>(`/chat/conversations/${id}`),
  createConversation: (title?: string) =>
    request<ConversationSummary>("/chat/conversations", { method: "POST", ...json({ title }) }),
  renameConversation: (id: string, title: string) =>
    request<ConversationSummary>(`/chat/conversations/${id}`, { method: "PATCH", ...json({ title }) }),
  deleteConversation: (id: string) => request<void>(`/chat/conversations/${id}`, { method: "DELETE" }),
  clearConversation: (id: string) => request<void>(`/chat/conversations/${id}/messages`, { method: "DELETE" }),

  // settings
  getSettings: () => request<SettingsResponse>("/settings"),
  updateSettings: (patch: Partial<RuntimeSettings>) =>
    request<SettingsResponse>("/settings", { method: "PUT", ...json(patch) }),
  resetSettings: () => request<SettingsResponse>("/settings/reset", { method: "POST" }),
  listModels: () => request<ModelsResponse>("/settings/models"),
};

export interface StreamHandlers {
  onMeta?: (data: { conversation_id: string; user_message: ChatMessage }) => void;
  onSources?: (data: { sources: Source[] }) => void;
  onToken?: (token: string) => void;
  onDone?: (message: ChatMessage) => void;
  onError?: (detail: string, message?: ChatMessage) => void;
}

export async function streamChat(
  body: { question: string; conversation_id?: string | null; document_ids?: string[] | null },
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: headers({ "Content-Type": "application/json", Accept: "text/event-stream" }),
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    throw new ApiError("Cannot reach the server. Is the backend running?", 0, "network_error");
  }
  if (!response.ok || !response.body) throw await parseError(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();

  const dispatch = (event: string, raw: string) => {
    const data = JSON.parse(raw);
    switch (event) {
      case "meta":
        handlers.onMeta?.(data);
        break;
      case "sources":
        handlers.onSources?.(data);
        break;
      case "token":
        handlers.onToken?.(data.t);
        break;
      case "done":
        handlers.onDone?.(data.message);
        break;
      case "error":
        handlers.onError?.(data.detail, data.message);
        break;
    }
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const ev of parser.push(decoder.decode(value, { stream: true }))) dispatch(ev.event, ev.data);
    }
    for (const ev of parser.flush()) dispatch(ev.event, ev.data);
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    throw err;
  }
}
