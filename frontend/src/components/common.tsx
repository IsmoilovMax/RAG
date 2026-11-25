import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  FileText,
  FileType2,
  Loader2,
  Presentation,
  RefreshCw,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { DocumentStatus, HealthStatus } from "@/lib/types";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const STATUS: Record<DocumentStatus, { label: string; variant: "success" | "info" | "warning" | "destructive"; icon: LucideIcon; spin?: boolean }> = {
  pending: { label: "Queued", variant: "warning", icon: Clock },
  processing: { label: "Processing", variant: "info", icon: Loader2, spin: true },
  ready: { label: "Ready", variant: "success", icon: CheckCircle2 },
  failed: { label: "Failed", variant: "destructive", icon: XCircle },
};

export function StatusBadge({ status, className }: { status: DocumentStatus; className?: string }) {
  const s = STATUS[status];
  const Icon = s.icon;
  return (
    <Badge variant={s.variant} className={className}>
      <Icon className={cn(s.spin && "animate-spin")} />
      {s.label}
    </Badge>
  );
}

const FILE_ICONS: Record<string, { icon: LucideIcon; color: string }> = {
  pdf: { icon: FileText, color: "text-red-500 bg-red-500/10" },
  docx: { icon: FileType2, color: "text-blue-500 bg-blue-500/10" },
  txt: { icon: FileText, color: "text-zinc-500 bg-zinc-500/10" },
  md: { icon: FileText, color: "text-zinc-500 bg-zinc-500/10" },
  csv: { icon: FileSpreadsheet, color: "text-emerald-600 bg-emerald-500/10" },
  xlsx: { icon: FileSpreadsheet, color: "text-emerald-600 bg-emerald-500/10" },
  pptx: { icon: Presentation, color: "text-orange-500 bg-orange-500/10" },
};

export function FileIcon({ type, className }: { type: string | null | undefined; className?: string }) {
  const entry = FILE_ICONS[type ?? ""] ?? FILE_ICONS.txt;
  const Icon = entry.icon;
  return (
    <span className={cn("inline-flex size-8 shrink-0 items-center justify-center rounded-md", entry.color, className)}>
      <Icon className="size-4" />
    </span>
  );
}

export function HealthDot({ status, className }: { status: HealthStatus | undefined; className?: string }) {
  const color =
    status === "ok" ? "bg-success" : status === "degraded" ? "bg-warning" : status === "error" ? "bg-destructive" : "bg-muted-foreground/40";
  return (
    <span className={cn("relative inline-flex size-2.5", className)}>
      {status === "ok" && <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-40", color)} />}
      <span className={cn("relative inline-flex size-2.5 rounded-full", color)} />
    </span>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 px-6 py-14 text-center", className)}>
      <div className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Icon className="size-6" />
      </div>
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  error,
  onRetry,
  className,
}: {
  title?: string;
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const message = error instanceof Error ? error.message : String(error ?? "Unknown error");
  return (
    <div className={cn("flex flex-col items-center justify-center gap-3 px-6 py-12 text-center", className)}>
      <div className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
        <AlertTriangle className="size-6" />
      </div>
      <div className="space-y-1">
        <p className="font-medium">{title}</p>
        <p className="max-w-md text-sm text-muted-foreground">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw /> Try again
        </Button>
      )}
    </div>
  );
}
