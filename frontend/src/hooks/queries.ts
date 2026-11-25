import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api } from "@/lib/api";
import type { DocumentStatus, RuntimeSettings } from "@/lib/types";

export const keys = {
  documents: (filters?: object) => ["documents", filters ?? {}] as const,
  document: (id: string) => ["document", id] as const,
  chunks: (id: string) => ["chunks", id] as const,
  stats: ["stats"] as const,
  readiness: ["readiness"] as const,
  settings: ["settings"] as const,
  models: ["models"] as const,
  conversations: ["conversations"] as const,
  conversation: (id: string) => ["conversation", id] as const,
};

const isBusy = (status: DocumentStatus) => status === "pending" || status === "processing";

export function useDocuments(filters: { status?: DocumentStatus; q?: string } = {}) {
  return useQuery({
    queryKey: keys.documents(filters),
    queryFn: () => api.listDocuments(filters),
    // Poll while anything is still being ingested.
    refetchInterval: (query) => (query.state.data?.items.some((d) => isBusy(d.status)) ? 1500 : false),
  });
}

export function useReadyDocuments() {
  return useQuery({
    queryKey: keys.documents({ status: "ready" }),
    queryFn: () => api.listDocuments({ status: "ready" }),
    staleTime: 10_000,
  });
}

export function useChunks(id: string | null) {
  return useQuery({
    queryKey: keys.chunks(id ?? ""),
    queryFn: () => api.getChunks(id!, 200),
    enabled: !!id,
  });
}

export function useStats() {
  return useQuery({
    queryKey: keys.stats,
    queryFn: api.stats,
    refetchInterval: (query) => (query.state.data?.processing_queue ? 2000 : 15_000),
  });
}

export function useReadiness() {
  return useQuery({ queryKey: keys.readiness, queryFn: api.readiness, refetchInterval: 20_000, retry: 1 });
}

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: api.getSettings });
}

export function useModels() {
  return useQuery({ queryKey: keys.models, queryFn: api.listModels, staleTime: 30_000 });
}

export function useConversations() {
  return useQuery({ queryKey: keys.conversations, queryFn: api.listConversations });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: keys.conversation(id ?? ""),
    queryFn: () => api.getConversation(id!),
    enabled: !!id,
  });
}

function useInvalidateDocuments() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["documents"] });
    qc.invalidateQueries({ queryKey: keys.stats });
    qc.invalidateQueries({ queryKey: keys.settings });
  };
}

export function useDeleteDocument() {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (doc: { id: string; filename: string }) => api.deleteDocument(doc.id),
    onSuccess: (_d, doc) => {
      toast.success(`Deleted “${doc.filename}”`);
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useReprocessDocument() {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (id: string) => api.reprocessDocument(id),
    onSuccess: (doc) => {
      toast.info(`Re-processing “${doc.filename}”`);
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useReindexAll() {
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: api.reindexAll,
    onSuccess: ({ queued }) => {
      toast.success(queued ? `Re-indexing ${queued} document${queued === 1 ? "" : "s"}` : "Nothing to re-index");
      invalidate();
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<RuntimeSettings>) => api.updateSettings(patch),
    onSuccess: (data) => {
      qc.setQueryData(keys.settings, data);
      qc.invalidateQueries({ queryKey: keys.readiness });
      toast.success("Settings saved");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useResetSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.resetSettings,
    onSuccess: (data) => {
      qc.setQueryData(keys.settings, data);
      toast.success("Settings reset to defaults");
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteConversation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.conversations });
      qc.invalidateQueries({ queryKey: keys.stats });
    },
    onError: (err: Error) => toast.error(err.message),
  });
}

export function useRenameConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.renameConversation(id, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.conversations }),
    onError: (err: Error) => toast.error(err.message),
  });
}
