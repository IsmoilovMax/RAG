import { useRef, useState } from "react";
import { ArrowUp, Files, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Textarea } from "@/components/ui/textarea";
import { useReadyDocuments } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const MAX_CHARS = 4000;

function ScopePicker({ scope, onChange }: { scope: string[]; onChange: (ids: string[]) => void }) {
  const { data } = useReadyDocuments();
  const docs = data?.items ?? [];
  const label = scope.length === 0 ? "All documents" : `${scope.length} document${scope.length === 1 ? "" : "s"}`;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm" className={cn("text-muted-foreground", scope.length && "text-primary")}>
          <Files /> {label}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 w-72 overflow-y-auto">
        <DropdownMenuLabel>Search within</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => onChange([])}>All ready documents ({docs.length})</DropdownMenuItem>
        {docs.length > 0 && <DropdownMenuSeparator />}
        {docs.map((d) => (
          <DropdownMenuCheckboxItem
            key={d.id}
            checked={scope.includes(d.id)}
            onSelect={(e) => e.preventDefault()}
            onCheckedChange={(checked) => onChange(checked ? [...scope, d.id] : scope.filter((id) => id !== d.id))}
          >
            <span className="truncate">{d.filename}</span>
          </DropdownMenuCheckboxItem>
        ))}
        {docs.length === 0 && <p className="px-2 py-2 text-xs text-muted-foreground">No processed documents yet.</p>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Composer({
  onSend,
  onStop,
  streaming,
  disabled,
  scope,
  onScopeChange,
}: {
  onSend: (question: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
  scope: string[];
  onScopeChange: (ids: string[]) => void;
}) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && !streaming && !disabled;

  const submit = () => {
    if (!canSend) return;
    onSend(value.trim());
    setValue("");
    ref.current?.focus();
  };

  return (
    <div className="rounded-2xl border bg-card shadow-sm transition-shadow focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
      <Textarea
        ref={ref}
        value={value}
        maxLength={MAX_CHARS}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder={disabled ? "Upload and process a document to start asking questions…" : "Ask a question about your documents…"}
        disabled={disabled}
        rows={1}
        className="max-h-48 min-h-12 resize-none border-0 bg-transparent px-4 pt-3.5 shadow-none focus-visible:ring-0 dark:bg-transparent"
        aria-label="Question"
      />
      <div className="flex items-center justify-between gap-2 px-2 pb-2">
        <ScopePicker scope={scope} onChange={onScopeChange} />
        <div className="flex items-center gap-2">
          {value.length > MAX_CHARS * 0.8 && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {value.length}/{MAX_CHARS}
            </span>
          )}
          {streaming ? (
            <Button size="icon-sm" variant="secondary" onClick={onStop} aria-label="Stop generating" className="rounded-full">
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button size="icon-sm" onClick={submit} disabled={!canSend} aria-label="Send question" className="rounded-full">
              <ArrowUp />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
