import { useDeferredValue, useState } from "react";
import { Download, Eye, FileSearch, FileText, MoreHorizontal, RefreshCw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { EmptyState, ErrorState, FileIcon, PageHeader, StatusBadge } from "@/components/common";
import { ChunksDialog } from "@/components/documents/chunks-dialog";
import { UploadDropzone } from "@/components/documents/upload-dropzone";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useDeleteDocument, useDocuments, useReindexAll, useReprocessDocument, useSettings } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { DocumentItem, DocumentStatus } from "@/lib/types";
import { formatBytes, timeAgo } from "@/lib/utils";

type StatusFilter = DocumentStatus | "all";

export default function DocumentsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const deferredQuery = useDeferredValue(query.trim());
  const { data, isLoading, isError, error, refetch, isFetching } = useDocuments({
    status: status === "all" ? undefined : status,
    q: deferredQuery || undefined,
  });
  const { data: settings } = useSettings();
  const deleteDoc = useDeleteDocument();
  const reprocess = useReprocessDocument();
  const reindex = useReindexAll();
  const [viewing, setViewing] = useState<DocumentItem | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<DocumentItem | null>(null);
  const [confirmReindex, setConfirmReindex] = useState(false);

  const filtered = !!deferredQuery || status !== "all";
  const items = data?.items ?? [];

  return (
    <>
      <PageHeader
        title="Documents"
        description="Upload, inspect and manage the files your assistant can answer from"
        actions={
          <Button variant="outline" onClick={() => setConfirmReindex(true)} disabled={reindex.isPending || !data?.total}>
            <RefreshCw className={reindex.isPending ? "animate-spin" : undefined} /> Re-index all
          </Button>
        }
      />

      <UploadDropzone
        maxUploadMb={settings?.system.max_upload_mb}
        maxFiles={settings?.system.max_files_per_upload}
        supportedTypes={settings?.system.supported_types}
      />

      <Card className="gap-0 py-0">
        <div className="flex flex-col gap-2 border-b p-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by file name or type…"
              className="pl-9"
              aria-label="Search documents"
            />
          </div>
          <Select value={status} onValueChange={(v) => setStatus(v as StatusFilter)}>
            <SelectTrigger className="sm:w-44" aria-label="Filter by status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="ready">Ready</SelectItem>
              <SelectItem value="processing">Processing</SelectItem>
              <SelectItem value="pending">Queued</SelectItem>
              <SelectItem value="failed">Failed</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="ghost" size="icon" onClick={() => refetch()} aria-label="Refresh">
            <RefreshCw className={isFetching ? "animate-spin" : undefined} />
          </Button>
        </div>

        {isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : isError ? (
          <ErrorState title="Could not load documents" error={error} onRetry={() => refetch()} />
        ) : items.length === 0 ? (
          filtered ? (
            <EmptyState icon={FileSearch} title="No matching documents" description="Try a different search or status filter." />
          ) : (
            <EmptyState
              icon={FileText}
              title="No documents yet"
              description="Upload PDFs, Word files, spreadsheets, presentations or text files to get started."
            />
          )
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Size</TableHead>
                <TableHead className="hidden sm:table-cell">Chunks</TableHead>
                <TableHead className="hidden lg:table-cell">Uploaded</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell className="max-w-[16rem] sm:max-w-sm">
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 text-left"
                      onClick={() => doc.status === "ready" && setViewing(doc)}
                    >
                      <FileIcon type={doc.file_type} />
                      <div className="min-w-0">
                        <p className="truncate font-medium" title={doc.filename}>
                          {doc.filename}
                        </p>
                        <p className="text-xs text-muted-foreground uppercase">
                          {doc.file_type}
                          {doc.page_count ? ` · ${doc.page_count} ${doc.file_type === "pptx" ? "slides" : doc.file_type === "xlsx" ? "sheets" : "pages"}` : ""}
                        </p>
                      </div>
                    </button>
                  </TableCell>
                  <TableCell>
                    <div className="w-36 space-y-1.5">
                      {doc.status === "failed" && doc.error_message ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span>
                              <StatusBadge status={doc.status} className="cursor-help" />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent>{doc.error_message}</TooltipContent>
                        </Tooltip>
                      ) : (
                        <StatusBadge status={doc.status} />
                      )}
                      {doc.status === "processing" && <Progress value={doc.progress} />}
                    </div>
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{formatBytes(doc.size_bytes)}</TableCell>
                  <TableCell className="hidden tabular-nums sm:table-cell">{doc.status === "ready" ? doc.chunk_count : "—"}</TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{timeAgo(doc.created_at)}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${doc.filename}`}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem disabled={doc.status !== "ready"} onSelect={() => setViewing(doc)}>
                          <Eye /> View chunks
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onSelect={() => api.downloadDocument(doc).catch((e: Error) => toast.error(e.message))}
                        >
                          <Download /> Download original
                        </DropdownMenuItem>
                        <DropdownMenuItem disabled={doc.status === "processing"} onSelect={() => reprocess.mutate(doc.id)}>
                          <RefreshCw /> Re-process
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(doc)}>
                          <Trash2 /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {data && data.total > 0 && (
          <div className="border-t px-4 py-2.5 text-xs text-muted-foreground">
            {data.total} document{data.total === 1 ? "" : "s"}
          </div>
        )}
      </Card>

      <ChunksDialog doc={viewing} onOpenChange={(open) => !open && setViewing(null)} />

      <AlertDialog open={!!confirmDelete} onOpenChange={(open) => !open && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete document?</AlertDialogTitle>
            <AlertDialogDescription>
              “{confirmDelete?.filename}” and all of its indexed chunks will be permanently removed. Past chat answers
              keep their citations as text.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => confirmDelete && deleteDoc.mutate({ id: confirmDelete.id, filename: confirmDelete.filename })}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmReindex} onOpenChange={setConfirmReindex}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Re-index all documents?</AlertDialogTitle>
            <AlertDialogDescription>
              Every document is re-parsed, re-chunked with the current chunking settings and re-embedded. This can take a
              while on CPU; documents remain listed while they are processed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => reindex.mutate()}>Re-index</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
