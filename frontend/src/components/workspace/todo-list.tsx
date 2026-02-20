import { CheckIcon, ChevronUpIcon, ListTodoIcon } from "lucide-react";

import type { Todo } from "@/core/todos";
import { cn } from "@/lib/utils";

import {
  QueueItem,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
} from "../ai-elements/queue";

export function TodoList({
  className,
  todos,
  collapsed = false,
  hidden = false,
  onToggle,
}: {
  className?: string;
  todos: Todo[];
  collapsed?: boolean;
  hidden?: boolean;
  onToggle?: () => void;
}) {
  const hasTodos = todos.length > 0;
  return (
    <div
      className={cn(
        "bg-sidebar flex h-fit w-full flex-col gap-2 rounded-lg border p-0.5 transition-all duration-200 ease-out",
        hidden ? "pointer-events-none translate-y-1 opacity-0" : "",
        className,
      )}
    >
      <header
        className={cn(
          "flex min-h-8 shrink-0 cursor-pointer items-center justify-between px-3 text-sm transition-all duration-300 ease-out",
        )}
        onClick={() => {
          onToggle?.();
        }}
      >
        <div className="text-muted-foreground">
          <div className="flex items-center justify-center gap-2">
            <ListTodoIcon className="size-4" />
            <div>To-dos</div>
          </div>
        </div>
        <div>
          <ChevronUpIcon
            className={cn(
              "text-muted-foreground size-4 transition-transform duration-300 ease-out",
              collapsed ? "" : "rotate-180",
            )}
          />
        </div>
      </header>
      <main
        className={cn(
          "flex grow px-1 transition-all duration-300 ease-out",
          collapsed ? "h-0 pb-3" : "h-40 pb-4",
        )}
      >
        {collapsed ? null : hasTodos ? (
          <QueueList className="mt-0 w-full">
            {todos.map((todo, i) => (
              <QueueItem key={i + (todo.content ?? "")}>
                <div className="flex items-start gap-2">
                  <QueueItemIndicator
                    className={cn(
                      "shrink-0",
                      todo.status === "in_progress" ? "bg-primary/70" : "",
                    )}
                    completed={todo.status === "completed"}
                  />
                  <QueueItemContent
                    className={cn(
                      "line-clamp-none whitespace-normal",
                      todo.status === "in_progress" ? "text-primary/70" : "",
                    )}
                    completed={todo.status === "completed"}
                  >
                    {todo.content}
                  </QueueItemContent>
                </div>
              </QueueItem>
            ))}
          </QueueList>
        ) : (
          <div className="flex w-full flex-col justify-center gap-3 px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="border-muted-foreground/40 bg-muted/40 text-muted-foreground flex size-8 items-center justify-center rounded-full border">
                <CheckIcon className="size-4" />
              </span>
              <span className="border-muted-foreground/40 bg-muted/40 text-muted-foreground flex size-8 items-center justify-center rounded-full border">
                <CheckIcon className="size-4" />
              </span>
              <span className="border-muted-foreground/40 bg-background flex size-8 items-center justify-center rounded-full border" />
            </div>
            <p className="text-muted-foreground text-sm">
              See task progress for longer tasks.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
