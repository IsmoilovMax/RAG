import { useState } from "react";
import { ChevronDown, Quote } from "lucide-react";
import { FileIcon } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import type { Source } from "@/lib/types";
import { cn } from "@/lib/utils";

export function sourceLocation(s: Source): string {
  const parts: string[] = [];
  if (s.section) parts.push(s.section);
  if (s.page != null && (s.file_type === "pdf" || !s.section)) parts.push(`Page ${s.page}`);
  return parts.join(" · ");
}

function SourceCard({ source, active, onSelect }: { source: Source; active: boolean; onSelect: () => void }) {
  const pct = Math.round(source.similarity * 100);
  const location = sourceLocation(source);
  return (
    <div
      id={`source-${source.document_id}-${source.chunk_index}`}
      className={cn(
        "rounded-lg border bg-card transition-all",
        active && "border-primary ring-2 ring-primary/20",
        !source.cited && !active && "opacity-75",
      )}
    >
      <button type="button" onClick={onSelect} className="flex w-full items-center gap-3 p-2.5 text-left">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
          {source.index}
        </span>
        <FileIcon type={source.file_type} className="size-7" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium" title={source.filename}>
            {source.filename}
          </p>
          <p className="truncate text-xs text-muted-foreground">{location || "Document"}</p>
        </div>
        <div className="hidden shrink-0 items-center gap-2 sm:flex">
          {source.inferred ? (
            <Badge variant="info" title="The answer did not cite passages; matched to this one by its wording">
              Matched
            </Badge>
          ) : source.cited ? (
            <Badge variant="success">Cited</Badge>
          ) : (
            <Badge variant="secondary">Retrieved</Badge>
          )}
          <div className="w-14 text-right" title="Semantic similarity to your question">
            <p className="text-xs font-medium tabular-nums">{pct}%</p>
            <div className="mt-0.5 h-1 overflow-hidden rounded-full bg-muted">
              <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
          </div>
        </div>
        <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", active && "rotate-180")} />
      </button>
      {active && (
        <div className="border-t px-3 py-2.5">
          <div className="flex gap-2">
            <Quote className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            <p className="text-sm whitespace-pre-wrap text-foreground/85">{source.snippet}</p>
          </div>
        </div>
      )}
    </div>
  );
}

export function SourceList({
  sources,
  activeIndex,
  onSelect,
}: {
  sources: Source[];
  activeIndex: number | null;
  onSelect: (index: number | null) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  if (!sources.length) return null;
  const cited = sources.filter((s) => s.cited).length;
  const verb = sources.some((s) => s.inferred) ? "matched" : "cited";
  // Clicking a citation chip for a hidden source expands the list.
  const expanded = showAll || (activeIndex != null && activeIndex > 3);
  const visible = expanded || sources.length <= 3 ? sources : sources.slice(0, 3);
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        Sources · {cited ? `${cited} ${verb} of ${sources.length} retrieved` : `${sources.length} retrieved`}
      </p>
      <div className="space-y-1.5">
        {visible.map((s) => (
          <SourceCard
            key={`${s.document_id}-${s.chunk_index}-${s.index}`}
            source={s}
            active={activeIndex === s.index}
            onSelect={() => onSelect(activeIndex === s.index ? null : s.index)}
          />
        ))}
      </div>
      {sources.length > 3 && (
        <button
          type="button"
          onClick={() => {
            if (expanded) onSelect(null);
            setShowAll(!expanded);
          }}
          className="text-xs font-medium text-primary hover:underline"
        >
          {expanded ? "Show fewer sources" : `Show ${sources.length - 3} more`}
        </button>
      )}
    </div>
  );
}
