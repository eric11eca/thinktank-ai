import { Minus, Square, X } from "lucide-react";

import { cn } from "@/lib/utils";

interface WindowControlsProps {
  className?: string;
}

/**
 * Custom window controls for Windows/Linux
 * On macOS, native traffic lights are used instead
 */
export function WindowControls({ className }: WindowControlsProps) {
  const platform = window.electronAPI?.platform;

  // Don't render on macOS (uses native traffic lights)
  if (platform === "darwin") {
    return null;
  }

  // Don't render if not in Electron
  if (!window.electronAPI) {
    return null;
  }

  return (
    <div className={cn("flex items-center", className)}>
      <button
        className="hover:bg-muted flex h-8 w-12 items-center justify-center transition-colors"
        onClick={() => window.electronAPI?.minimize()}
        title="Minimize"
      >
        <Minus className="h-4 w-4" />
      </button>
      <button
        className="hover:bg-muted flex h-8 w-12 items-center justify-center transition-colors"
        onClick={() => window.electronAPI?.maximize()}
        title="Maximize"
      >
        <Square className="h-3 w-3" />
      </button>
      <button
        className="flex h-8 w-12 items-center justify-center transition-colors hover:bg-red-500 hover:text-white"
        onClick={() => window.electronAPI?.close()}
        title="Close"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
