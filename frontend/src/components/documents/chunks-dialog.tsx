import { Layers } from "lucide-react";
import { EmptyState, ErrorState, FileIcon } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useChunks } from "@/hooks/queries";
import type { DocumentItem } from "@/lib/types";
import { formatBytes, formatDate, formatDuration } from "@/lib/utils";

export function ChunksDialog({ doc, onOpenChange }: { doc: DocumentItem | null; onOpenChange: (open: boolean) => void }) {
  const { data, isLoading, isError, error, refetch } = useChunks(doc?.id ?? null);

  return (
    <Dialog open={!!doc} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-3xl">
        {doc && (
          <>
            <DialogHeader>
              <div className="flex items-center gap-3 pr-6">
                <FileIcon type={doc.file_type} />
                <div className="min-w-0">
                  <DialogTitle className="truncate">{doc.filename}</DialogTitle>
                  <DialogDescription>
                    {formatBytes(doc.size_bytes)} · {doc.page_count ? `${doc.page_count} pages/sections · ` : ""}
                    {doc.chunk_count} chunks · processed in {formatDuration(doc.processing_ms)}
                  </DialogDescription>
                </div>
              </div>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
              {[
                ["Chunk size", doc.chunk_size ?? "—"],
                ["Overlap", doc.chunk_overlap ?? "—"],
                ["Characters", doc.char_count?.toLocaleString() ?? "—"],
                ["Processed", formatDate(doc.processed_at)],
              ].map(([k, v]) => (
                <div key={k as string} className="rounded-md border px-3 py-2">
                  <p className="text-muted-foreground">{k}</p>
                  <p className="truncate font-medium">{v}</p>
                </div>
              ))}
            </div>
            <ScrollArea className="min-h-0 flex-1 rounded-md border">
              <div className="space-y-3 p-3">
                {isLoading && Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
                {isError && <ErrorState error={error} onRetry={() => refetch()} />}
                {data && data.items.length === 0 && (
                  <EmptyState icon={Layers} title="No chunks" description="This document has not been indexed yet." />
                )}
                {data?.items.map((chunk) => (
                  <div key={chunk.id} className="rounded-lg border bg-muted/30 p-3">
                    <div className="mb-2 flex flex-wrap items-center gap-1.5">
                      <Badge variant="secondary">#{Number(chunk.metadata.chunk_index) + 1}</Badge>
                      {chunk.metadata.section && <Badge variant="outline">{String(chunk.metadata.section)}</Badge>}
                      {chunk.metadata.page != null && !chunk.metadata.section && (
                        <Badge variant="outline">Page {String(chunk.metadata.page)}</Badge>
                      )}
                      <span className="ml-auto text-xs text-muted-foreground">{chunk.text.length} chars</span>
                    </div>
                    <p className="text-sm whitespace-pre-wrap text-foreground/90">{chunk.text}</p>
                  </div>
                ))}
                {data && data.total > data.items.length && (
                  <p className="text-center text-xs text-muted-foreground">
                    Showing first {data.items.length} of {data.total} chunks
                  </p>
                )}
              </div>
            </ScrollArea>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
