import { useCallback, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CloudUpload, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { keys } from "@/hooks/queries";
import { api } from "@/lib/api";
import { cn, formatBytes } from "@/lib/utils";

const DEFAULT_TYPES = ["pdf", "docx", "txt", "md", "csv", "xlsx", "pptx"];

export function UploadDropzone({
  maxUploadMb = 50,
  maxFiles = 20,
  supportedTypes = DEFAULT_TYPES,
}: {
  maxUploadMb?: number;
  maxFiles?: number;
  supportedTypes?: string[];
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<{ count: number; progress: number } | null>(null);
  const qc = useQueryClient();

  const upload = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      if (!files.length) return;

      const accepted: File[] = [];
      for (const f of files) {
        const ext = f.name.split(".").pop()?.toLowerCase() ?? "";
        if (!supportedTypes.includes(ext)) {
          toast.error(`“${f.name}”: unsupported file type`, { description: `Allowed: ${supportedTypes.join(", ")}` });
        } else if (f.size > maxUploadMb * 1024 * 1024) {
          toast.error(`“${f.name}” is too large`, { description: `${formatBytes(f.size)} exceeds the ${maxUploadMb} MB limit` });
        } else if (f.size === 0) {
          toast.error(`“${f.name}” is empty`);
        } else {
          accepted.push(f);
        }
      }
      if (!accepted.length) return;

      const batches: File[][] = [];
      for (let i = 0; i < accepted.length; i += maxFiles) batches.push(accepted.slice(i, i + maxFiles));

      setUploading({ count: accepted.length, progress: 0 });
      try {
        let done = 0;
        for (const batch of batches) {
          const res = await api.uploadDocuments(batch, (fraction) =>
            setUploading({ count: accepted.length, progress: ((done + fraction * batch.length) / accepted.length) * 100 }),
          );
          done += batch.length;
          for (const r of res.results) {
            if (r.status === "accepted") toast.success(`Uploaded “${r.filename}”`, { description: "Processing in the background…" });
            else if (r.status === "duplicate") toast.warning(`Skipped duplicate “${r.filename}”`, { description: r.error ?? undefined });
            else toast.error(`Rejected “${r.filename}”`, { description: r.error ?? undefined });
          }
        }
      } catch (err) {
        toast.error((err as Error).message);
      } finally {
        setUploading(null);
        qc.invalidateQueries({ queryKey: ["documents"] });
        qc.invalidateQueries({ queryKey: keys.stats });
      }
    },
    [maxFiles, maxUploadMb, qc, supportedTypes],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!uploading) setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!uploading) void upload(e.dataTransfer.files);
      }}
      className={cn(
        "relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed bg-card px-6 py-10 text-center transition-colors",
        dragging ? "border-primary bg-primary/5" : "border-border hover:border-primary/50",
      )}
    >
      <div className={cn("flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary", dragging && "scale-110 transition-transform")}>
        {uploading ? <Loader2 className="size-6 animate-spin" /> : <CloudUpload className="size-6" />}
      </div>
      {uploading ? (
        <div className="w-full max-w-xs space-y-2">
          <p className="text-sm font-medium">
            Uploading {uploading.count} file{uploading.count === 1 ? "" : "s"}…
          </p>
          <Progress value={uploading.progress} />
        </div>
      ) : (
        <>
          <div className="space-y-1">
            <p className="font-medium">Drop files here or browse</p>
            <p className="text-sm text-muted-foreground">
              {supportedTypes.map((t) => t.toUpperCase()).join(", ")} · up to {maxUploadMb} MB each
            </p>
          </div>
          <Button onClick={() => inputRef.current?.click()}>Choose files</Button>
        </>
      )}
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        accept={supportedTypes.map((t) => `.${t}`).join(",")}
        onChange={(e) => {
          if (e.target.files) void upload(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
