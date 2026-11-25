import { useState } from "react";
import { Check, MessageSquare, MoreHorizontal, Pencil, Plus, Trash2, X } from "lucide-react";
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
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useConversations, useDeleteConversation, useRenameConversation } from "@/hooks/queries";
import type { ConversationSummary } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

export function ConversationList({
  activeId,
  onSelect,
  onNew,
  onDeleted,
}: {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDeleted: (id: string) => void;
}) {
  const { data, isLoading, isError } = useConversations();
  const del = useDeleteConversation();
  const rename = useRenameConversation();
  const [editing, setEditing] = useState<{ id: string; title: string } | null>(null);
  const [confirm, setConfirm] = useState<ConversationSummary | null>(null);

  const saveRename = () => {
    if (editing && editing.title.trim()) rename.mutate({ id: editing.id, title: editing.title.trim() });
    setEditing(null);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="p-3">
        <Button onClick={onNew} className="w-full justify-start" variant="outline">
          <Plus /> New chat
        </Button>
      </div>
      <p className="px-4 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">History</p>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-0.5 p-2">
          {isLoading && Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 w-full" />)}
          {isError && <p className="px-2 py-4 text-xs text-destructive">Could not load conversations.</p>}
          {data?.length === 0 && (
            <div className="flex flex-col items-center gap-2 px-3 py-8 text-center text-xs text-muted-foreground">
              <MessageSquare className="size-5" />
              Your conversations will appear here.
            </div>
          )}
          {data?.map((c) =>
            editing?.id === c.id ? (
              <div key={c.id} className="flex items-center gap-1 px-1 py-0.5">
                <Input
                  autoFocus
                  value={editing.title}
                  maxLength={255}
                  onChange={(e) => setEditing({ id: c.id, title: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveRename();
                    if (e.key === "Escape") setEditing(null);
                  }}
                  className="h-8 text-sm"
                  aria-label="Conversation title"
                />
                <Button size="icon-sm" variant="ghost" onClick={saveRename} aria-label="Save title">
                  <Check />
                </Button>
                <Button size="icon-sm" variant="ghost" onClick={() => setEditing(null)} aria-label="Cancel rename">
                  <X />
                </Button>
              </div>
            ) : (
              <div
                key={c.id}
                className={cn(
                  "group flex items-center rounded-md transition-colors",
                  activeId === c.id ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
                )}
              >
                <button type="button" onClick={() => onSelect(c.id)} className="min-w-0 flex-1 px-3 py-2 text-left">
                  <p className="truncate text-sm">{c.title}</p>
                  <p className="text-[11px] text-muted-foreground">{timeAgo(c.updated_at)}</p>
                </button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="mr-1 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
                      aria-label={`Options for ${c.title}`}
                    >
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => setEditing({ id: c.id, title: c.title })}>
                      <Pencil /> Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem variant="destructive" onSelect={() => setConfirm(c)}>
                      <Trash2 /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ),
          )}
        </div>
      </ScrollArea>

      <AlertDialog open={!!confirm} onOpenChange={(open) => !open && setConfirm(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>“{confirm?.title}” and all of its messages will be permanently deleted.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (!confirm) return;
                const id = confirm.id;
                del.mutate(id, { onSuccess: () => onDeleted(id) });
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
