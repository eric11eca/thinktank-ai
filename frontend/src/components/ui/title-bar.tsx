import { cn } from "@/lib/utils";

import { WindowControls } from "./window-controls";

/**
 * Native-style title bar for Electron.
 * - macOS: transparent drag region; native traffic lights are shown by the OS at trafficLightPosition {x:16, y:16}
 * - Windows/Linux: themed bar with custom close/minimize/maximize controls
 * Renders nothing outside of Electron.
 */
export function TitleBar({ className }: { className?: string }) {
  if (typeof window === "undefined" || !window.electronAPI) return null;

  return (
    <div
      className={cn(
        "fixed top-0 right-0 left-0 z-50 flex h-10 select-none items-center",
        "border-border/50 bg-background/80 border-b backdrop-blur-sm",
        className,
      )}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      style={{ WebkitAppRegion: "drag" } as any}
    >
      {/* Space for macOS native traffic lights positioned at x:16 */}
      <div className="w-20" />

      {/* Custom controls for Windows/Linux; renders null on macOS */}
      <div
        className="ml-auto"
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        style={{ WebkitAppRegion: "no-drag" } as any}
      >
        <WindowControls />
      </div>
    </div>
  );
}
