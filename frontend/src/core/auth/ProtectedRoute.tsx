import { Navigate } from "react-router";

import { env } from "@/env";

import { useAuth } from "./context";

/**
 * Route wrapper that redirects unauthenticated users to /login.
 * In Electron mode, auth is bypassed entirely.
 */
export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  // Electron mode: no auth required
  if (env.IS_ELECTRON) {
    return <>{children}</>;
  }

  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center">
        <div className="border-primary h-8 w-8 animate-spin rounded-full border-4 border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
