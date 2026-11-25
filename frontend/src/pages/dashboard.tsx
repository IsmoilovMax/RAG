import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Boxes,
  Cpu,
  Database,
  FileText,
  Gauge,
  MessageSquare,
  Sparkles,
  Upload,
  type LucideIcon,
} from "lucide-react";
import { EmptyState, ErrorState, FileIcon, HealthDot, PageHeader, StatusBadge } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useReadiness, useStats } from "@/hooks/queries";
import type { ComponentHealth, StatsResponse } from "@/lib/types";
import { formatBytes, formatDuration, timeAgo } from "@/lib/utils";

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  loading,
}: {
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
  hint?: string;
  loading?: boolean;
}) {
  return (
    <Card className="gap-3">
      <CardContent className="flex items-start justify-between gap-3">
        <div className="space-y-1.5">
          <p className="text-sm text-muted-foreground">{label}</p>
          {loading ? <Skeleton className="h-8 w-20" /> : <p className="text-3xl font-semibold tracking-tight">{value}</p>}
          {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        </div>
        <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Icon className="size-5" />
        </div>
      </CardContent>
    </Card>
  );
}

const COMPONENTS: Record<string, { label: string; icon: LucideIcon }> = {
  database: { label: "Database", icon: Database },
  vector_store: { label: "Vector store (ChromaDB)", icon: Boxes },
  embeddings: { label: "Embedding model", icon: Cpu },
  llm: { label: "Local LLM (Ollama)", icon: Sparkles },
};

function describe(name: string, c: ComponentHealth): string {
  if (c.detail) return c.detail;
  if (name === "database") return `Backend: ${String(c.info.backend)}`;
  if (name === "vector_store") return `${String(c.info.vectors)} vectors indexed`;
  if (name === "embeddings") return `${String(c.info.model)} loaded on CPU`;
  if (name === "llm") return `${String(c.info.model)} · Ollama ${String(c.info.ollama_version ?? "")}`;
  return "Operational";
}

function HealthCard() {
  const { data, isLoading, isError, error, refetch } = useReadiness();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="size-4 text-muted-foreground" /> System health
        </CardTitle>
        <CardDescription>All inference runs locally on CPU</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading &&
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full" />)}
        {isError && <ErrorState title="Backend unreachable" error={error} onRetry={() => refetch()} className="py-6" />}
        {data &&
          Object.entries(COMPONENTS).map(([name, meta]) => {
            const c = data.components[name];
            if (!c) return null;
            const Icon = meta.icon;
            return (
              <div key={name} className="flex items-center gap-3 rounded-lg border p-3">
                <Icon className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{meta.label}</p>
                  <p className="truncate text-xs text-muted-foreground" title={describe(name, c)}>
                    {describe(name, c)}
                  </p>
                </div>
                <HealthDot status={c.status} />
              </div>
            );
          })}
      </CardContent>
    </Card>
  );
}

function Bar({ label, value, total, className }: { label: string; value: number; total: number; className: string }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span>{label}</span>
        <span className="text-muted-foreground tabular-nums">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full transition-all duration-700 ${className}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function AnswerQuality({ stats }: { stats: StatsResponse }) {
  const a = stats.answers_by_type;
  const total = stats.questions_answered;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Answer grounding</CardTitle>
        <CardDescription>How questions were resolved against your documents</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {total === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No questions asked yet.</p>
        ) : (
          <>
            <Bar label="Answered from documents" value={a.grounded ?? 0} total={total} className="bg-success" />
            <Bar label="Context found, but insufficient" value={a.insufficient ?? 0} total={total} className="bg-warning" />
            <Bar label="No relevant context" value={a.no_context ?? 0} total={total} className="bg-muted-foreground/50" />
            <Bar label="Errors" value={a.error ?? 0} total={total} className="bg-destructive" />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Library({ stats }: { stats: StatsResponse }) {
  const s = stats.documents_by_status;
  const types = Object.entries(stats.documents_by_type).sort((x, y) => y[1] - x[1]);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Library</CardTitle>
        <CardDescription>{formatBytes(stats.total_size_bytes)} stored</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Bar label="Ready" value={s.ready ?? 0} total={stats.documents_total} className="bg-success" />
        <Bar label="Queued / processing" value={(s.pending ?? 0) + (s.processing ?? 0)} total={stats.documents_total} className="bg-primary" />
        <Bar label="Failed" value={s.failed ?? 0} total={stats.documents_total} className="bg-destructive" />
        {types.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {types.map(([type, n]) => (
              <Badge key={type} variant="secondary" className="uppercase">
                {type} · {n}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function GettingStarted() {
  const steps = [
    { icon: Upload, title: "Upload documents", text: "PDF, DOCX, TXT, CSV, XLSX or PPTX files", to: "/documents" },
    { icon: Cpu, title: "Automatic indexing", text: "Text is chunked and embedded locally on CPU", to: "/documents" },
    { icon: MessageSquare, title: "Ask questions", text: "Get cited answers grounded in your files", to: "/chat" },
  ];
  return (
    <Card className="overflow-hidden">
      <CardContent className="grid gap-6 md:grid-cols-[1.2fr_2fr] md:items-center">
        <div className="space-y-3">
          <Badge variant="info">
            <Sparkles /> Getting started
          </Badge>
          <h2 className="text-xl font-semibold">Turn your documents into answers</h2>
          <p className="text-sm text-muted-foreground">
            DocuMind retrieves the most relevant passages from your files and answers only from them — with sources.
          </p>
          <Button asChild>
            <Link to="/documents">
              <Upload /> Upload your first document
            </Link>
          </Button>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          {steps.map((s, i) => (
            <Link key={s.title} to={s.to} className="rounded-lg border p-4 transition-colors hover:bg-accent/40">
              <div className="mb-3 flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                  {i + 1}
                </span>
                <s.icon className="size-4 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">{s.title}</p>
              <p className="mt-1 text-xs text-muted-foreground">{s.text}</p>
            </Link>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading, isError, error, refetch } = useStats();

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Overview of your knowledge base and assistant activity"
        actions={
          <>
            <Button variant="outline" asChild>
              <Link to="/documents">
                <Upload /> Upload
              </Link>
            </Button>
            <Button asChild>
              <Link to="/chat">
                <MessageSquare /> Ask a question
              </Link>
            </Button>
          </>
        }
      />

      {isError ? (
        <Card>
          <ErrorState title="Could not load statistics" error={error} onRetry={() => refetch()} />
        </Card>
      ) : (
        <>
          {stats && stats.documents_total === 0 && <GettingStarted />}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              icon={FileText}
              label="Documents"
              loading={isLoading}
              value={stats?.documents_total ?? 0}
              hint={stats?.processing_queue ? `${stats.processing_queue} processing now` : `${stats?.documents_by_status.ready ?? 0} ready`}
            />
            <StatCard icon={Boxes} label="Indexed chunks" loading={isLoading} value={stats?.vector_count ?? 0} hint="Vectors in ChromaDB" />
            <StatCard
              icon={MessageSquare}
              label="Questions answered"
              loading={isLoading}
              value={stats?.questions_answered ?? 0}
              hint={`${stats?.conversations ?? 0} conversations`}
            />
            <StatCard
              icon={Gauge}
              label="Avg. response time"
              loading={isLoading}
              value={formatDuration(stats?.avg_latency_ms ?? null)}
              hint="Retrieval + generation"
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Recent documents</CardTitle>
                  <CardDescription>Latest uploads and their processing status</CardDescription>
                </CardHeader>
                <CardContent>
                  {isLoading ? (
                    <div className="space-y-2">
                      {Array.from({ length: 4 }).map((_, i) => (
                        <Skeleton key={i} className="h-12 w-full" />
                      ))}
                    </div>
                  ) : stats && stats.recent_documents.length > 0 ? (
                    <div className="divide-y">
                      {stats.recent_documents.map((d) => (
                        <div key={d.id} className="flex items-center gap-3 py-2.5">
                          <FileIcon type={d.file_type} />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">{d.filename}</p>
                            <p className="text-xs text-muted-foreground">
                              {d.chunk_count} chunks · {timeAgo(d.created_at)}
                            </p>
                          </div>
                          <StatusBadge status={d.status} />
                        </div>
                      ))}
                      <div className="pt-3">
                        <Button variant="ghost" size="sm" asChild>
                          <Link to="/documents">
                            View all documents <ArrowRight />
                          </Link>
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <EmptyState icon={FileText} title="No documents yet" description="Upload files to build your knowledge base." className="py-8" />
                  )}
                </CardContent>
              </Card>
              {stats && (
                <div className="grid gap-4 md:grid-cols-2">
                  <Library stats={stats} />
                  <AnswerQuality stats={stats} />
                </div>
              )}
            </div>
            <HealthCard />
          </div>
        </>
      )}
    </>
  );
}
