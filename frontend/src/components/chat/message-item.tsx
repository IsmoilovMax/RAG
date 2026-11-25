import { memo, useMemo, useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { AlertTriangle, Bot, Check, Copy, FileQuestion, Lightbulb, Loader2, User } from "lucide-react";
import { linkCitations, splitExplanation } from "@/components/chat/answer-content";
import { SourceList, sourceLocation } from "@/components/chat/source-list";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ChatMessage, Source } from "@/lib/types";
import { cn, formatDuration } from "@/lib/utils";

export interface UIMessage extends ChatMessage {
  pending?: boolean;
}

function useMarkdownComponents(sources: Source[], onCite: (n: number) => void): Components {
  return useMemo(
    () => ({
      a: ({ href, children, ...props }) => {
        if (href?.startsWith("#cite-")) {
          const n = Number(href.slice(6));
          const source = sources.find((s) => s.index === n);
          return (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => onCite(n)}
                  className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] -translate-y-px items-center justify-center rounded bg-primary/12 px-1 align-middle text-[0.7rem] font-semibold text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
                >
                  {n}
                </button>
              </TooltipTrigger>
              {source && (
                <TooltipContent>
                  {source.filename}
                  {sourceLocation(source) ? ` · ${sourceLocation(source)}` : ""}
                </TooltipContent>
              )}
            </Tooltip>
          );
        }
        return (
          <a href={href} target="_blank" rel="noreferrer noopener" className="text-primary underline" {...props}>
            {children}
          </a>
        );
      },
    }),
    [sources, onCite],
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
      aria-label="Copy answer"
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function AssistantBody({ message }: { message: UIMessage }) {
  const [activeSource, setActiveSource] = useState<number | null>(null);
  const answerType = message.meta?.answer_type;
  const sources = message.sources ?? [];
  const components = useMarkdownComponents(sources, setActiveSource);
  const { answer, explanation } = useMemo(() => splitExplanation(message.content), [message.content]);

  if (message.pending && !message.content) {
    return (
      <div className="flex items-center gap-2 py-1 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        {sources.length ? `Found ${sources.length} relevant passage${sources.length === 1 ? "" : "s"} — generating answer…` : "Searching your documents…"}
      </div>
    );
  }

  if (answerType === "error") {
    return (
      <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
        <div>
          <p className="font-medium text-destructive">The answer could not be generated</p>
          <p className="mt-0.5 text-muted-foreground">{message.content}</p>
        </div>
      </div>
    );
  }

  if (answerType === "no_context") {
    const r = message.meta.retrieval;
    return (
      <div className="flex items-start gap-3 rounded-lg border border-dashed bg-muted/40 p-3 text-sm">
        <FileQuestion className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
        <div className="space-y-1">
          <p className="font-medium">{message.content}</p>
          <p className="text-muted-foreground">
            No passage was similar enough to your question
            {r?.best_similarity != null && message.meta.similarity_threshold != null
              ? ` (best match ${Math.round(r.best_similarity * 100)}% vs. ${Math.round(message.meta.similarity_threshold * 100)}% threshold)`
              : ""}
            , so no answer was generated. Try rephrasing, or upload a document that covers this topic.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {answerType === "insufficient" && (
        <div className="flex items-center gap-2 text-xs font-medium text-warning">
          <AlertTriangle className="size-3.5" /> The retrieved passages did not contain enough information
        </div>
      )}
      <div className={cn("prose-chat", message.pending && "typing-caret")}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {linkCitations(answer, sources.length)}
        </ReactMarkdown>
      </div>
      {explanation && (
        <div className="rounded-lg border border-warning/30 bg-warning/8 p-3">
          <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-warning">
            <Lightbulb className="size-3.5" /> AI explanation — not stated directly in your documents
          </p>
          <div className="prose-chat text-foreground/85">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
              {linkCitations(explanation, sources.length)}
            </ReactMarkdown>
          </div>
        </div>
      )}
      {!message.pending && <SourceList sources={sources} activeIndex={activeSource} onSelect={setActiveSource} />}
      {!message.pending && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <CopyButton text={message.content} />
          {message.meta?.model && <span>{message.meta.model}</span>}
          {message.meta?.latency_ms != null && <span>{formatDuration(message.meta.latency_ms)}</span>}
          {message.meta?.interrupted && <span className="text-warning">Stopped early</span>}
        </div>
      )}
    </div>
  );
}

export const MessageItem = memo(function MessageItem({ message }: { message: UIMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-secondary text-secondary-foreground" : "bg-primary text-primary-foreground",
        )}
      >
        {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
      </div>
      <div className={cn("min-w-0", isUser ? "max-w-[85%]" : "flex-1")}>
        {isUser ? (
          <div className="rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-sm whitespace-pre-wrap text-primary-foreground">
            {message.content}
          </div>
        ) : (
          <div className="pt-1">
            <AssistantBody message={message} />
          </div>
        )}
      </div>
    </div>
  );
});
