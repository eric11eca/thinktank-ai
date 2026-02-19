import { createBrowserRouter, createHashRouter, Navigate, useParams } from "react-router";

import { App } from "./App";
import { Landing } from "./pages/Landing";
import { WorkspaceLayout } from "./pages/WorkspaceLayout";
import { Chat } from "./pages/Chat";
import { ChatList } from "./pages/ChatList";
import { env } from "./env";

/**
 * Wrapper component that forces Chat to remount when threadId changes.
 * This ensures the useStream hook properly resets for different threads.
 */
function ChatWrapper() {
  const { threadId } = useParams<{ threadId: string }>();
  return <Chat key={threadId} />;
}

/**
 * React Router configuration
 * Uses HashRouter for Electron (file:// protocol compatibility)
 * Uses BrowserRouter for web
 */
const createRouter = env.IS_ELECTRON ? createHashRouter : createBrowserRouter;

export const router = createRouter([
  {
    path: "/",
    element: <App />,
    children: [
      {
        index: true,
        element: <Landing />,
      },
      {
        path: "workspace",
        element: <WorkspaceLayout />,
        children: [
          {
            index: true,
            element: <Navigate to="/workspace/chats/new" replace />,
          },
          {
            path: "chats",
            element: <ChatList />,
          },
          {
            path: "chats/:threadId",
            element: <ChatWrapper />,
          },
        ],
      },
    ],
  },
]);
