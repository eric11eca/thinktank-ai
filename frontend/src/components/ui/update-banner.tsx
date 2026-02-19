import { Download, RefreshCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface UpdateInfo {
  version: string;
  releaseDate?: string;
  releaseNotes?: string;
}

interface DownloadProgress {
  percent: number;
  bytesPerSecond: number;
  total: number;
  transferred: number;
}

type UpdateState = "idle" | "available" | "downloading" | "downloaded";

export function UpdateBanner() {
  const [state, setState] = useState<UpdateState>("idle");
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [progress, setProgress] = useState<DownloadProgress | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!window.electronAPI) return;

    const cleanupFns: (() => void)[] = [];

    // Listen for update events
    cleanupFns.push(
      window.electronAPI.on("update:available", (info: unknown) => {
        setUpdateInfo(info as UpdateInfo);
        setState("available");
      })
    );

    cleanupFns.push(
      window.electronAPI.on("update:progress", (prog: unknown) => {
        setProgress(prog as DownloadProgress);
        setState("downloading");
      })
    );

    cleanupFns.push(
      window.electronAPI.on("update:downloaded", () => {
        setState("downloaded");
        setProgress(null);
      })
    );

    return () => {
      cleanupFns.forEach((fn) => fn());
    };
  }, []);

  const handleDownload = async () => {
    await window.electronAPI?.downloadUpdate();
  };

  const handleInstall = () => {
    window.electronAPI?.installUpdate();
  };

  if (!window.electronAPI || state === "idle" || dismissed) {
    return null;
  }

  return (
    <div
      className={cn(
        "bg-primary text-primary-foreground fixed top-0 right-0 left-0 z-50 flex items-center justify-between px-4 py-2",
        state === "downloaded" && "bg-green-600"
      )}
    >
      <div className="flex items-center gap-3">
        {state === "available" && (
          <>
            <RefreshCw className="h-4 w-4" />
            <span>
              Update available: v{updateInfo?.version}
            </span>
          </>
        )}
        {state === "downloading" && (
          <>
            <Download className="h-4 w-4 animate-bounce" />
            <span>Downloading update...</span>
            {progress && (
              <Progress value={progress.percent} className="w-32 bg-white/20" />
            )}
            <span className="text-sm opacity-80">
              {progress?.percent.toFixed(0)}%
            </span>
          </>
        )}
        {state === "downloaded" && (
          <>
            <RefreshCw className="h-4 w-4" />
            <span>Update ready to install (v{updateInfo?.version})</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        {state === "available" && (
          <Button
            size="sm"
            variant="secondary"
            onClick={handleDownload}
            className="h-7"
          >
            Download
          </Button>
        )}
        {state === "downloaded" && (
          <Button
            size="sm"
            variant="secondary"
            onClick={handleInstall}
            className="h-7"
          >
            Restart to Install
          </Button>
        )}
        <button
          className="hover:bg-white/10 rounded p-1 transition-colors"
          onClick={() => setDismissed(true)}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
