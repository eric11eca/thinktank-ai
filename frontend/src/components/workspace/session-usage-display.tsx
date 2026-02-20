import { ArrowDownIcon, ArrowUpIcon } from "lucide-react";

import type { TokenUsage } from "@/core/threads/types";

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function SessionUsageDisplay({
  usage,
}: {
  usage: TokenUsage | undefined;
}) {
  if (
    !usage ||
    (usage.input_tokens === 0 && usage.output_tokens === 0)
  ) {
    return null;
  }

  return (
    <span className="text-muted-foreground/50 ml-3 inline-flex items-center gap-2 text-xs tabular-nums">
      <span className="flex items-center gap-1">
        <ArrowUpIcon className="size-3" />
        {formatTokens(usage.input_tokens)}
      </span>
      <span className="text-muted-foreground/40">·</span>
      <span className="flex items-center gap-1">
        <ArrowDownIcon className="size-3" />
        {formatTokens(usage.output_tokens)}
      </span>
    </span>
  );
}
