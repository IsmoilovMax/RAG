import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { BookOpenCheck, Eraser, History, MessageSquare, ShieldCheck, Upload } from "lucide-react";
import { toast } from "sonner";
import { Composer } from "@/components/chat/composer";
import { ConversationList } from "@/components/chat/conversation-list";
import { MessageItem, type UIMessage } from "@/components/chat/message-item";
import { ErrorState } from "@/components/common";
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
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { keys, useConversation, useReadyDocuments } from "@/hooks/queries";
import { api, streamChat } from "@/lib/api";

const SUGGESTIONS = [
  "Summarize the key points of my documents",
  "What policies or rules are described?",
  "List the most important numbers and figures",
  "What are the main products or services mentioned?",
];

function now() {
  return new Date().toISOString();
}

export default function ChatPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const activeId = conversationId ?? null;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const conversation = useConversation(activeId);
  const { data: readyDocs, isLoading: docsLoading } = useReadyDocuments();

  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [scope, setScope] = useState<string[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);

  // Sync from the server whenever we're not in the middle of streaming.
  useEffect(() => {
    if (streaming) return;
    setMessages(activeId ? (conversation.data?.messages ?? []) : []);
  }, [conversation.data, activeId, streaming]);

  // Abort any in-flight stream when leaving the page.
  useEffect(() => () => abortRef.current?.abort(), []);

  // Auto-scroll while streaming, unless the user scrolled up.
  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const updateDraft = useCallback((fn: (m: UIMessage) => UIMessage) => {
    setMessages((prev) => prev.map((m) => (m.id === "draft" ? fn(m) : m)));
  }, []);

  const send = useCallback(
    async (question: string) => {
      const controller = new AbortController();
      abortRef.current = controller;
      stickToBottom.current = true;
      setStreaming(true);
      let convId = activeId;
      const base = { conversation_id: activeId ?? "", sources: [], meta: {}, created_at: now() };
      setMessages((prev) => [
        ...prev,
        { ...base, id: "pending-user", role: "user", content: question },
        { ...base, id: "draft", role: "assistant", content: "", pending: true },
      ]);

      try {
        await streamChat(
          { question, conversation_id: activeId, document_ids: scope.length ? scope : null },
          {
            onMeta: ({ conversation_id, user_message }) => {
              convId = conversation_id;
              setMessages((prev) => prev.map((m) => (m.id === "pending-user" ? user_message : m)));
              if (!activeId) navigate(`/chat/${conversation_id}`, { replace: true });
              void qc.invalidateQueries({ queryKey: keys.conversations });
            },
            onSources: ({ sources }) => updateDraft((m) => ({ ...m, sources })),
            onToken: (t) => updateDraft((m) => ({ ...m, content: m.content + t })),
            onDone: (message) => setMessages((prev) => prev.map((m) => (m.id === "draft" ? message : m))),
            onError: (detail, message) => {
              toast.error(detail);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === "draft"
                    ? (message ?? { ...m, pending: false, content: detail, meta: { answer_type: "error", error: detail } })
                    : m,
                ),
              );
            },
          },
          controller.signal,
        );
        if (controller.signal.aborted) {
          updateDraft((m) => ({ ...m, pending: false, meta: { ...m.meta, interrupted: true } }));
        }
      } catch (err) {
        const detail = (err as Error).message;
        toast.error(detail);
        updateDraft((m) => ({ ...m, pending: false, content: detail, meta: { answer_type: "error", error: detail } }));
      } finally {
        abortRef.current = null;
        if (convId) await qc.invalidateQueries({ queryKey: keys.conversation(convId) });
        void qc.invalidateQueries({ queryKey: keys.conversations });
        void qc.invalidateQueries({ queryKey: keys.stats });
        setStreaming(false);
      }
    },
    [activeId, navigate, qc, scope, updateDraft],
  );

  const stop = () => abortRef.current?.abort();

  const newChat = () => {
    if (streaming) stop();
    setHistoryOpen(false);
    navigate("/chat");
  };

  const clearChat = async () => {
    if (!activeId) return;
    try {
      await api.clearConversation(activeId);
      await qc.invalidateQueries({ queryKey: keys.conversation(activeId) });
      void qc.invalidateQueries({ queryKey: keys.conversations });
      toast.success("Chat cleared");
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const noDocuments = !docsLoading && (readyDocs?.total ?? 0) === 0;
  const notFound = conversation.isError;
  const list = (
    <ConversationList
      activeId={activeId}
      onSelect={(id) => {
        if (streaming) stop();
        setHistoryOpen(false);
        navigate(`/chat/${id}`);
      }}
      onNew={newChat}
      onDeleted={(id) => {
        if (id === activeId) navigate("/chat");
      }}
    />
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r lg:block">{list}</aside>
      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="h-[80vh] p-0 sm:max-w-sm">
          <DialogTitle className="sr-only">Conversation history</DialogTitle>
          {list}
        </DialogContent>
      </Dialog>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          <Button variant="ghost" size="icon-sm" className="lg:hidden" onClick={() => setHistoryOpen(true)} aria-label="Show history">
            <History />
          </Button>
          <h1 className="min-w-0 flex-1 truncate text-sm font-medium">
            {activeId ? (conversation.data?.title ?? "Conversation") : "New conversation"}
          </h1>
          <div className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:flex">
            <ShieldCheck className="size-3.5 text-success" /> Answers only from your documents
          </div>
          {activeId && messages.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)} disabled={streaming}>
              <Eraser /> Clear
            </Button>
          )}
        </div>

        <div
          ref={scrollRef}
          className="min-h-0 flex-1 overflow-y-auto"
          onScroll={(e) => {
            const el = e.currentTarget;
            stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {notFound ? (
              <ErrorState
                title="Conversation not found"
                error={conversation.error}
                onRetry={() => navigate("/chat")}
              />
            ) : activeId && conversation.isLoading ? (
              <div className="space-y-6">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="space-y-2">
                    <Skeleton className="ml-auto h-10 w-1/2" />
                    <Skeleton className="h-20 w-full" />
                  </div>
                ))}
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center gap-6 py-10 text-center sm:py-16">
                <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  {noDocuments ? <Upload className="size-7" /> : <BookOpenCheck className="size-7" />}
                </div>
                <div className="space-y-2">
                  <h2 className="text-xl font-semibold">{noDocuments ? "No documents to search yet" : "Ask your documents anything"}</h2>
                  <p className="mx-auto max-w-md text-sm text-muted-foreground">
                    {noDocuments
                      ? "Upload at least one document and wait for it to finish processing, then come back to ask questions."
                      : "Answers are generated by a local model using only passages retrieved from your files, with citations you can inspect."}
                  </p>
                </div>
                {noDocuments ? (
                  <Button asChild>
                    <Link to="/documents">
                      <Upload /> Upload documents
                    </Link>
                  </Button>
                ) : (
                  <div className="grid w-full max-w-xl gap-2 sm:grid-cols-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => void send(s)}
                        className="flex items-start gap-2 rounded-xl border bg-card p-3 text-left text-sm transition-colors hover:bg-accent/50"
                      >
                        <MessageSquare className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-7">
                {messages.map((m) => (
                  <MessageItem key={m.id} message={m} />
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="shrink-0 px-4 pb-4">
          <div className="mx-auto w-full max-w-3xl space-y-2">
            <Composer
              onSend={(q) => void send(q)}
              onStop={stop}
              streaming={streaming}
              disabled={noDocuments || notFound}
              scope={scope}
              onScopeChange={setScope}
            />
            <p className="text-center text-[11px] text-muted-foreground">
              Runs fully on your machine. Verify important answers against the cited sources.
            </p>
          </div>
        </div>
      </section>

      <AlertDialog open={confirmClear} onOpenChange={setConfirmClear}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Clear this chat?</AlertDialogTitle>
            <AlertDialogDescription>All messages in this conversation will be deleted. This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void clearChat()}>
              Clear chat
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
