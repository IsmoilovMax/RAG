import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Eye, EyeOff, KeyRound, Monitor, Moon, RefreshCw, RotateCcw, Save, Server, Sun } from "lucide-react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { ErrorState, PageHeader } from "@/components/common";
import { useTheme, type Theme } from "@/components/theme-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Slider } from "@/components/ui/slider";
import { useModels, useReindexAll, useResetSettings, useSettings, useUpdateSettings } from "@/hooks/queries";
import { getApiKey, setApiKey } from "@/lib/api";
import type { RuntimeSettings } from "@/lib/types";
import { cn, formatBytes } from "@/lib/utils";

function Field({
  label,
  hint,
  value,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  value?: React.ReactNode;
  children: React.ReactNode;
  htmlFor?: string;
}) {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={htmlFor}>{label}</Label>
        {value != null && <span className="text-sm font-medium text-muted-foreground tabular-nums">{value}</span>}
      </div>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function NumberInput({
  id,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  id: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
}) {
  return (
    <Input
      id={id}
      type="number"
      inputMode="numeric"
      min={min}
      max={max}
      step={step}
      value={Number.isFinite(value) ? value : ""}
      onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
      aria-invalid={!Number.isFinite(value) || value < min || value > max}
    />
  );
}

function ModelPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data, isLoading, refetch, isFetching } = useModels();
  const models = data?.models ?? [];
  const known = models.some((m) => m.name === value);
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        {data?.available && models.length > 0 ? (
          <Select value={value} onValueChange={onChange}>
            <SelectTrigger id="llm_model">
              <SelectValue placeholder="Select a model" />
            </SelectTrigger>
            <SelectContent>
              {!known && <SelectItem value={value}>{value} (not installed)</SelectItem>}
              {models.map((m) => (
                <SelectItem key={m.name} value={m.name}>
                  {m.name}
                  <span className="ml-2 text-xs text-muted-foreground">
                    {[m.parameter_size, m.quantization, m.size_bytes ? formatBytes(m.size_bytes) : null].filter(Boolean).join(" · ")}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Input id="llm_model" value={value} onChange={(e) => onChange(e.target.value)} placeholder="qwen2.5:3b" disabled={isLoading} />
        )}
        <Button variant="outline" size="icon" onClick={() => refetch()} aria-label="Refresh model list">
          <RefreshCw className={cn(isFetching && "animate-spin")} />
        </Button>
      </div>
      {data && !data.available && (
        <p className="flex items-center gap-1.5 text-xs text-warning">
          <AlertTriangle className="size-3.5" /> {data.error ?? "Ollama is not reachable"} — enter a model name manually.
        </p>
      )}
      {data?.available && !known && (
        <p className="text-xs text-warning">
          “{value}” is not installed. Run <code className="rounded bg-muted px-1">ollama pull {value}</code>
        </p>
      )}
    </div>
  );
}

const THEMES: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

function AppearanceCard() {
  const { theme, setTheme } = useTheme();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>Choose how DocuMind looks on this device</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-3 gap-2">
        {THEMES.map(({ value, label, icon: Icon }) => (
          <button
            key={value}
            type="button"
            onClick={() => setTheme(value)}
            className={cn(
              "flex flex-col items-center gap-2 rounded-lg border p-3 text-sm transition-colors",
              theme === value ? "border-primary bg-primary/5 text-primary" : "hover:bg-accent/50",
            )}
          >
            <Icon className="size-5" />
            {label}
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

function ApiKeyCard({ authEnabled }: { authEnabled: boolean }) {
  const [key, setKey] = useState(getApiKey);
  const [visible, setVisible] = useState(false);
  const qc = useQueryClient();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4 text-muted-foreground" /> API key
        </CardTitle>
        <CardDescription>
          {authEnabled
            ? "The server requires an API key. It is stored only in this browser."
            : "The server is not configured with an API key (open access)."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Input
              type={visible ? "text" : "password"}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="Paste API key"
              autoComplete="off"
              aria-label="API key"
            />
            <button
              type="button"
              onClick={() => setVisible((v) => !v)}
              className="absolute top-1/2 right-2.5 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label={visible ? "Hide key" : "Show key"}
            >
              {visible ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
          <Button
            variant="outline"
            onClick={() => {
              setApiKey(key.trim());
              void qc.invalidateQueries();
              toast.success(key.trim() ? "API key saved in this browser" : "API key removed");
            }}
          >
            Save
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { data, isLoading, isError, error, refetch } = useSettings();
  const update = useUpdateSettings();
  const reset = useResetSettings();
  const reindex = useReindexAll();
  const [form, setForm] = useState<RuntimeSettings | null>(null);

  useEffect(() => {
    if (data) setForm(data.settings);
  }, [data]);

  const dirty = useMemo(
    () => !!form && !!data && (Object.keys(form) as (keyof RuntimeSettings)[]).some((k) => form[k] !== data.settings[k]),
    [form, data],
  );

  const set = <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) =>
    setForm((f) => (f ? { ...f, [key]: value } : f));

  const invalid =
    !!form &&
    (Object.values(form).some((v) => typeof v === "number" && !Number.isFinite(v)) ||
      form.chunk_overlap >= form.chunk_size ||
      !form.llm_model.trim());

  const save = () => {
    if (!form || !data) return;
    const patch = Object.fromEntries(
      (Object.keys(form) as (keyof RuntimeSettings)[]).filter((k) => form[k] !== data.settings[k]).map((k) => [k, form[k]]),
    ) as Partial<RuntimeSettings>;
    update.mutate(patch);
  };

  if (isError) {
    return (
      <>
        <PageHeader title="Settings" />
        <Card>
          <ErrorState title="Could not load settings" error={error} onRetry={() => refetch()} />
        </Card>
        <ApiKeyCard authEnabled />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Settings"
        description="Tune retrieval, generation and chunking. Changes apply immediately to new questions."
        actions={
          <>
            <Button variant="outline" onClick={() => reset.mutate()} disabled={reset.isPending || isLoading}>
              <RotateCcw /> Reset to defaults
            </Button>
            <Button onClick={save} disabled={!dirty || invalid || update.isPending}>
              <Save /> {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </>
        }
      />

      {isLoading || !form || !data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-72 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Language model</CardTitle>
              <CardDescription>Local generation via Ollama (CPU)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <Field label="Model" htmlFor="llm_model" hint={`Default from environment: ${data.defaults.llm_model}`}>
                <ModelPicker value={form.llm_model} onChange={(v) => set("llm_model", v)} />
              </Field>
              <Field label="Temperature" value={form.llm_temperature.toFixed(2)} hint="Lower values produce more deterministic, faithful answers.">
                <Slider min={0} max={1} step={0.05} value={[form.llm_temperature]} onValueChange={([v]) => set("llm_temperature", v)} />
              </Field>
              <Field
                label="Conversation memory"
                value={`${form.history_turns} turn${form.history_turns === 1 ? "" : "s"}`}
                hint="How many earlier questions are used to understand follow-ups such as “and what about the other one?”."
              >
                <Slider min={0} max={10} step={1} value={[form.history_turns]} onValueChange={([v]) => set("history_turns", v)} />
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Retrieval</CardTitle>
              <CardDescription>Controls which passages are given to the model</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <Field
                label="Similarity threshold"
                value={`${Math.round(form.similarity_threshold * 100)}%`}
                hint="Passages below this cosine similarity are discarded. If none pass, the assistant says the documents lack the information."
              >
                <Slider min={0.2} max={0.9} step={0.01} value={[form.similarity_threshold]} onValueChange={([v]) => set("similarity_threshold", v)} />
              </Field>
              <Field
                label="Relative cutoff"
                value={`${Math.round(form.relative_score_cutoff * 100)}%`}
                hint="Drop passages scoring this far below the best match, keeping context focused."
              >
                <Slider min={0} max={0.5} step={0.01} value={[form.relative_score_cutoff]} onValueChange={([v]) => set("relative_score_cutoff", v)} />
              </Field>
              <div className="grid grid-cols-2 gap-4">
                <Field label="Top K passages" htmlFor="top_k">
                  <NumberInput id="top_k" value={form.retrieval_top_k} min={1} max={20} onChange={(v) => set("retrieval_top_k", v)} />
                </Field>
                <Field label="Max context (chars)" htmlFor="max_ctx">
                  <NumberInput id="max_ctx" value={form.max_context_chars} min={500} max={50000} step={500} onChange={(v) => set("max_context_chars", v)} />
                </Field>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Chunking</CardTitle>
              <CardDescription>Applies to newly processed documents</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <Field label="Chunk size (chars)" htmlFor="chunk_size">
                  <NumberInput id="chunk_size" value={form.chunk_size} min={100} max={8000} step={50} onChange={(v) => set("chunk_size", v)} />
                </Field>
                <Field label="Overlap (chars)" htmlFor="chunk_overlap">
                  <NumberInput id="chunk_overlap" value={form.chunk_overlap} min={0} max={2000} step={10} onChange={(v) => set("chunk_overlap", v)} />
                </Field>
              </div>
              {form.chunk_overlap >= form.chunk_size && (
                <p className="text-xs text-destructive">Overlap must be smaller than the chunk size.</p>
              )}
              {data.stale_documents > 0 && (
                <div className="flex flex-col gap-3 rounded-lg border border-warning/30 bg-warning/8 p-3 sm:flex-row sm:items-center">
                  <AlertTriangle className="size-4 shrink-0 text-warning" />
                  <p className="flex-1 text-sm">
                    {data.stale_documents} document{data.stale_documents === 1 ? " was" : "s were"} indexed with different chunk settings.
                  </p>
                  <Button size="sm" variant="outline" onClick={() => reindex.mutate()} disabled={reindex.isPending}>
                    <RefreshCw className={cn(reindex.isPending && "animate-spin")} /> Re-index
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="size-4 text-muted-foreground" /> System
              </CardTitle>
              <CardDescription>Configured through environment variables</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2.5 text-sm">
                {[
                  ["Embedding model", data.system.embedding_model],
                  ["Embedding batch size", data.system.embedding_batch_size],
                  ["Ollama URL", data.system.ollama_base_url],
                  ["LLM context window", `${data.system.ollama_num_ctx.toLocaleString()} tokens`],
                  ["Database", data.system.database_backend],
                  ["Upload limit", `${data.system.max_upload_mb} MB · ${data.system.max_files_per_upload} files`],
                  ["Environment", data.system.environment],
                ].map(([k, v]) => (
                  <div key={k as string} className="flex items-center justify-between gap-4">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="truncate text-right font-medium" title={String(v)}>
                      {v}
                    </dd>
                  </div>
                ))}
                <Separator className="my-3" />
                <div className="flex flex-wrap gap-1.5">
                  {data.system.supported_types.map((t) => (
                    <Badge key={t} variant="secondary" className="uppercase">
                      {t}
                    </Badge>
                  ))}
                </div>
              </dl>
            </CardContent>
          </Card>

          <AppearanceCard />
          <ApiKeyCard authEnabled={data.system.auth_enabled} />
        </div>
      )}
    </>
  );
}
