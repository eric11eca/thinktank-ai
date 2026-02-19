"use client";

import { ChevronDownIcon } from "lucide-react";
import { useState, type HTMLAttributes } from "react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

const MAX_LINES_COLLAPSED = 8;

export function CollapsibleCodeBlock({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLPreElement>) {
  const [isOpen, setIsOpen] = useState(false);

  // Count lines in the code
  const codeContent =
    typeof children === "object" &&
    children &&
    "props" in children &&
    typeof children.props === "object" &&
    children.props &&
    "children" in children.props
      ? String(children.props.children)
      : "";

  const lineCount = codeContent ? codeContent.split("\n").length : 0;
  const shouldShowToggle = lineCount > MAX_LINES_COLLAPSED;

  // If no toggle needed, render normally
  if (!shouldShowToggle) {
    return <pre className={cn(className)} {...props}>{children}</pre>;
  }

  const hiddenLines = lineCount - MAX_LINES_COLLAPSED;

  return (
    <Collapsible
      open={isOpen}
      onOpenChange={setIsOpen}
      className="not-prose group/code-block relative"
    >
      <div className="relative">
        {/* Expand/collapse button positioned at bottom-left when collapsed */}
        {!isOpen && (
          <>
            <pre
              className={cn(
                "relative max-h-[300px] overflow-hidden",
                className,
              )}
              {...props}
            >
              {children}
              {/* Gradient overlay */}
              <div className="absolute right-0 bottom-0 left-0 h-20 bg-gradient-to-t from-[var(--color-code-bg)] to-transparent pointer-events-none" />
            </pre>
            {/* Expand button at bottom */}
            <CollapsibleTrigger asChild>
              <button className="w-full border-t border-border bg-muted/30 py-2 text-center text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <ChevronDownIcon className="size-3" />
                  {hiddenLines} more lines
                </span>
              </button>
            </CollapsibleTrigger>
          </>
        )}

        {/* Expanded state */}
        {isOpen && (
          <CollapsibleContent>
            <pre className={cn(className)} {...props}>
              {children}
            </pre>
            {/* Collapse button at bottom */}
            <CollapsibleTrigger asChild>
              <button className="w-full border-t border-border bg-muted/30 py-2 text-center text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground">
                <span className="inline-flex items-center gap-1.5">
                  <ChevronDownIcon className="size-3 rotate-180" />
                  Less lines
                </span>
              </button>
            </CollapsibleTrigger>
          </CollapsibleContent>
        )}
      </div>
    </Collapsible>
  );
}
