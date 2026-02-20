# Code Change Summary (file diff, line-by-line)

Based on the complete `git diff HEAD`, list all changes by file. Deleted/added files are described separately.

---

## I. Backend

### 1. `backend/CLAUDE.md`

```diff
@@ -156,7 +156,7 @@ FastAPI application on port 8001 with health check at `GET /health`.
 | **Skills** (`/api/skills`) | `GET /` - list skills; `GET /{name}` - details; `PUT /{name}` - update enabled; `POST /install` - install from .skill archive |
 | **Memory** (`/api/memory`) | `GET /` - memory data; `POST /reload` - force reload; `GET /config` - config; `GET /status` - config + data |
 | **Uploads** (`/api/threads/{id}/uploads`) | `POST /` - upload files (auto-converts PDF/PPT/Excel/Word); `GET /list` - list; `DELETE /{filename}` - delete |
-| **Artifacts** (`/api/threads/{id}/artifacts`) | `GET /{path}` - serve artifacts; `?download=true` for download with citation removal |
+| **Artifacts** (`/api/threads/{id}/artifacts`) | `GET /{path}` - serve artifacts; `?download=true` for file download |

 Proxied through nginx: `/api/langgraph/*` -> LangGraph, all other `/api/*` -> Gateway.
```

- **Line 159**: In the table, the Artifacts description changed from "download with citation removal" to "file download".

---

### 2. `backend/src/agents/lead_agent/prompt.py`

```diff
@@ -240,34 +240,8 @@ You have access to skills that provide optimized workflows for specific tasks. E
 - Action-Oriented: Focus on delivering results, not explaining processes
 </response_style>

-<citations_format>
-After web_search, ALWAYS include citations in your output:
-
-1. Start with a `<citations>` block in JSONL format listing all sources
-2. In content, use FULL markdown link format: [Short Title](full_url)
-
-**CRITICAL - Citation Link Format:**
-- CORRECT: `[TechCrunch](https://techcrunch.com/ai-trends)` - full markdown link with URL
-- WRONG: `[arXiv:2502.19166]` - missing URL, will NOT render as link
-- WRONG: `[Source]` - missing URL, will NOT render as link
-
-**Rules:**
-- Every citation MUST be a complete markdown link with URL: `[Title](https://...)`
-- Write content naturally, add citation link at end of sentence/paragraph
-- NEVER use bare brackets like `[arXiv:xxx]` or `[Source]` without URL
-
-**Example:**
-<citations>
-{{"id": "cite-1", "title": "AI Trends 2026", "url": "https://techcrunch.com/ai-trends", "snippet": "Tech industry predictions"}}
-{{"id": "cite-2", "title": "OpenAI Research", "url": "https://openai.com/research", "snippet": "Latest AI research developments"}}
-</citations>
-The key AI trends for 2026 include enhanced reasoning capabilities and multimodal integration [TechCrunch](https://techcrunch.com/ai-trends). Recent breakthroughs in language models have also accelerated progress [OpenAI](https://openai.com/research).
-</citations_format>
-
-
 <critical_reminders>
 - **Clarification First**: ALWAYS clarify unclear/missing/ambiguous requirements BEFORE starting work - never assume or guess
-- **Web search citations**: When you use web_search (or synthesize subagent results that used it), you MUST output the `<citations>` block and [Title](url) links as specified in citations_format so citations display for the user.
 {subagent_reminder}- Skill First: Always load the relevant skill before starting **complex** tasks.
```

```diff
@@ -341,7 +315,6 @@ def apply_prompt_template(subagent_enabled: bool = False) -> str:
     # Add subagent reminder to critical_reminders if enabled
     subagent_reminder = (
         "- **Orchestrator Mode**: You are a task orchestrator - decompose complex tasks into parallel sub-tasks and launch multiple subagents simultaneously. Synthesize results, don't execute directly.\n"
-        "- **Citations when synthesizing**: When you synthesize subagent results that used web search or cite sources, you MUST include a consolidated `<citations>` block (JSONL format) and use [Title](url) markdown links in your response so citations display correctly.\n"
         if subagent_enabled
         else ""
     )
```

- **Deleted**: Entire `<citations_format>...</citations_format>` block (approx lines 243-266), the "Web search citations" item in `critical_reminders`, and the "Citations when synthesizing" line in `apply_prompt_template`.

---

### 3. `backend/src/gateway/routers/artifacts.py`

```diff
@@ -1,12 +1,10 @@
-import json
 import mimetypes
-import re
 import zipfile
 from pathlib import Path
 from urllib.parse import quote

-from fastapi import APIRouter, HTTPException, Request, Response
-from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
+from fastapi import APIRouter, HTTPException, Request
+from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response

 from src.gateway.path_utils import resolve_thread_virtual_path
```

- **Line 1**: removed `import json`.
- **Line 3**: removed `import re`.
- **Lines 6-7**: removed `Response` from `fastapi`; added `Response` to `fastapi.responses` (kept for binary inline responses).

```diff
@@ -24,40 +22,6 @@ def is_text_file_by_content(path: Path, sample_size: int = 8192) -> bool:
         return False


-def _extract_citation_urls(content: str) -> set[str]:
-    """Extract URLs from <citations> JSONL blocks. Format must match frontend core/citations/utils.ts."""
-    urls: set[str] = set()
-    for match in re.finditer(r"<citations>([\s\S]*?)</citations>", content):
-        for line in match.group(1).split("\n"):
-            line = line.strip()
-            if line.startswith("{"):
-                try:
-                    obj = json.loads(line)
-                    if "url" in obj:
-                        urls.add(obj["url"])
-                except (json.JSONDecodeError, ValueError):
-                    pass
-    return urls
-
-
-def remove_citations_block(content: str) -> str:
-    """Remove ALL citations from markdown (blocks, [cite-N], and citation links). Used for downloads."""
-    if not content:
-        return content
-
-    citation_urls = _extract_citation_urls(content)
-
-    result = re.sub(r"<citations>[\s\S]*?</citations>", "", content)
-    if "<citations>" in result:
-        result = re.sub(r"<citations>[\s\S]*$", "", result)
-    result = re.sub(r"\[cite-\d+\]", "", result)
-
-    for url in citation_urls:
-        result = re.sub(rf"\[[^\]]+\]\({re.escape(url)}\)", "", result)
-
-    return re.sub(r"\n{3,}", "\n\n", result).strip()
-
-
 def _extract_file_from_skill_archive(zip_path: Path, internal_path: str) -> bytes | None:
```

- **Deleted**: `_extract_citation_urls` and `remove_citations_block` (approx lines 25-62).

```diff
@@ -172,24 +136,9 @@ async def get_artifact(thread_id: str, path: str, request: Request) -> FileRespo

     # Encode filename for Content-Disposition header (RFC 5987)
     encoded_filename = quote(actual_path.name)
-
-    # Check if this is a markdown file that might contain citations
-    is_markdown = mime_type == "text/markdown" or actual_path.suffix.lower() in [".md", ".markdown"]
-
+
     # if `download` query parameter is true, return the file as a download
     if request.query_params.get("download"):
-        # For markdown files, remove citations block before download
-        if is_markdown:
-            content = actual_path.read_text()
-            clean_content = remove_citations_block(content)
-            return Response(
-                content=clean_content.encode("utf-8"),
-                media_type="text/markdown",
-                headers={
-                    "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
-                    "Content-Type": "text/markdown; charset=utf-8"
-                }
-            )
         return FileResponse(path=actual_path, filename=actual_path.name, media_type=mime_type, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"})

     if mime_type and mime_type == "text/html":
```

- **Deleted**: `is_markdown` check and the "for markdown, read file + remove_citations_block + Response" branch; downloads now always use `FileResponse`.

---

### 4. `backend/src/subagents/builtins/general_purpose.py`

```diff
@@ -24,21 +24,10 @@ Do NOT use for simple, single-step operations.""",
 - Do NOT ask for clarification - work with the information provided
 </guidelines>

-<citations_format>
-If you used web_search (or similar) and cite sources, ALWAYS include citations in your output:
-1. Start with a `<citations>` block in JSONL format listing all sources (one JSON object per line)
-2. In content, use FULL markdown link format: [Short Title](full_url)
-- Every citation MUST be a complete markdown link with URL: [Title](https://...)
-- Example block:
-<citations>
-{"id": "cite-1", "title": "...", "url": "https://...", "snippet": "..."}
-</citations>
-</citations_format>
-
 <output_format>
 When you complete the task, provide:
 1. A brief summary of what was accomplished
-2. Key findings or results (with citation links when from web search)
+2. Key findings or results
 3. Any relevant file paths, data, or artifacts created
 4. Issues encountered (if any)
 </output_format>
```

- **Deleted**: Entire `<citations_format>...</citations_format>` block.
- **Line 40**: item 2 changed from "Key findings or results (with citation links when from web search)" to "Key findings or results".

---

## II. Frontend Docs and Tools

### 5. `frontend/AGENTS.md`

```diff
@@ -49,7 +49,6 @@ src/
 ├── core/                   # Core business logic
 │   ├── api/                # API client & data fetching
 │   ├── artifacts/          # Artifact management
-│   ├── citations/          # Citation handling
 │   ├── config/              # App configuration
 │   ├── i18n/               # Internationalization
```

- **Line 52**: removed the `citations/` line from the directory tree.

---

### 6. `frontend/CLAUDE.md`

```diff
@@ -30,7 +30,7 @@ Frontend (Next.js) --> LangGraph SDK --> LangGraph Backend (lead_age
                                               └── Tools & Skills
 ```

-The frontend is a stateful chat application. Users create **threads** (conversations), send messages, and receive streamed AI responses. The backend orchestrates agents that can produce **artifacts** (files/code), **todos**, and **citations**.
+The frontend is a stateful chat application. Users create **threads** (conversations), send messages, and receive streamed AI responses. The backend orchestrates agents that can produce **artifacts** (files/code) and **todos**.

 ### Source Layout (`src/`)
```

- **Line 33**: removed "and **citations**".

---

### 7. `frontend/README.md`

```diff
@@ -89,7 +89,6 @@ src/
 ├── core/                   # Core business logic
 │   ├── api/                # API client & data fetching
 │   ├── artifacts/          # Artifact management
-│   ├── citations/          # Citation handling
 │   ├── config/              # App configuration
 │   ├── i18n/               # Internationalization
```

- **Line 92**: removed the `citations/` line from the directory tree.

---

### 8. `frontend/src/lib/utils.ts`

```diff
@@ -8,5 +8,5 @@ export function cn(...inputs: ClassValue[]) {
 /** Shared class for external links (underline by default). */
 export const externalLinkClass =
   "text-primary underline underline-offset-2 hover:no-underline";
-/** For streaming / loading state when link may be a citation (no underline). */
+/** Link style without underline by default (e.g. for streaming/loading). */
 export const externalLinkClassNoUnderline = "text-primary hover:underline";
```

- **Line 11**: comment-only update; exported value unchanged.

---

## III. Frontend Components

### 9. `frontend/src/components/workspace/artifacts/artifact-file-detail.tsx`

```diff
@@ -8,7 +8,6 @@ import {
   SquareArrowOutUpRightIcon,
   XIcon,
 } from "lucide-react";
-import * as React from "react";
 import { useCallback, useEffect, useMemo, useState } from "react";
 ...
@@ -21,7 +20,6 @@ import (
   ArtifactHeader,
   ArtifactTitle,
 } from "@/components/ai-elements/artifact";
-import { createCitationMarkdownComponents } from "@/components/ai-elements/inline-citation";
 import { Select, SelectItem } from "@/components/ui/select";
 ...
@@ -33,12 +31,6 @@ import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
 import { CodeEditor } from "@/components/workspace/code-editor";
 import { useArtifactContent } from "@/core/artifacts/hooks";
 import { urlOfArtifact } from "@/core/artifacts/utils";
-import type { Citation } from "@/core/citations";
-import {
-  contentWithoutCitationsFromParsed,
-  removeAllCitations,
-  useParsedCitations,
-} from "@/core/citations";
 import { useI18n } from "@/core/i18n/hooks";
 ...
@@ -48,9 +40,6 @@ import { cn } from "@/lib/utils";

 import { Tooltip } from "../tooltip";

-import { SafeCitationContent } from "../messages/safe-citation-content";
-import { useThread } from "../messages/context";
-
 import { useArtifacts } from "./context";
```

```diff
@@ -92,22 +81,13 @@ export function ArtifactFileDetail({
   const previewable = useMemo(() => {
     return (language === "html" && !isWriteFile) || language === "markdown";
   }, [isWriteFile, language]);
-  const { thread } = useThread();
   const { content } = useArtifactContent({
     threadId,
     filepath: filepathFromProps,
     enabled: isCodeFile && !isWriteFile,
   });

-  const parsed = useParsedCitations(
-    language === "markdown" ? (content ?? "") : "",
-  );
-  const cleanContent =
-    language === "markdown" && content ? parsed.cleanContent : (content ?? "");
-  const contentWithoutCitations =
-    language === "markdown" && content
-      ? contentWithoutCitationsFromParsed(parsed)
-      : (content ?? "");
+  const displayContent = content ?? "";

   const [viewMode, setViewMode] = useState<"code" | "preview">("code");
```

```diff
@@ -219,7 +199,7 @@ export function ArtifactFileDetail({
                 disabled={!content}
                 onClick={async () => {
                   try {
-                    await navigator.clipboard.writeText(contentWithoutCitations ?? "");
+                    await navigator.clipboard.writeText(displayContent ?? "");
                     toast.success(t.clipboard.copiedToClipboard);
 ...
@@ -255,27 +235,17 @@ export function ArtifactFileDetail({
           viewMode === "preview" &&
           language === "markdown" &&
           content && (
-            <SafeCitationContent
-              content={content}
-              isLoading={thread.isLoading}
-              rehypePlugins={streamdownPlugins.rehypePlugins}
-              className="flex size-full items-center justify-center p-4 my-0"
-              renderBody={(p) => (
-                <ArtifactFilePreview
-                  filepath={filepath}
-                  threadId={threadId}
-                  content={content}
-                  language={language ?? "text"}
-                  cleanContent={p.cleanContent}
-                  citationMap={p.citationMap}
-                />
-              )}
-            />
+            <ArtifactFilePreview
+              filepath={filepath}
+              threadId={threadId}
+              content={displayContent}
+              language={language ?? "text"}
+            />
           )}
         {isCodeFile && viewMode === "code" && (
           <CodeEditor
             className="size-full resize-none rounded-none border-none"
-            value={cleanContent ?? ""}
+            value={displayContent ?? ""}
             readonly
           />
         )}
```

```diff
@@ -295,29 +265,17 @@ export function ArtifactFilePreview({
   threadId,
   content,
   language,
-  cleanContent,
-  citationMap,
 }: {
   filepath: string;
   threadId: string;
   content: string;
   language: string;
-  cleanContent: string;
-  citationMap: Map<string, Citation>;
 }) {
   if (language === "markdown") {
-    const components = createCitationMarkdownComponents({
-      citationMap,
-      syntheticExternal: true,
-    });
     return (
       <div className="size-full px-4">
-        <Streamdown
-          className="size-full"
-          {...streamdownPlugins}
-          components={components}
-        >
-          {cleanContent ?? ""}
+        <Streamdown className="size-full" {...streamdownPlugins}>
+          {content ?? ""}
         </Streamdown>
       </div>
     );
```

- Removed React namespace, inline-citation, core/citations, SafeCitationContent, useThread; removed parsed/cleanContent/contentWithoutCitations and citation parsing logic.
- Added `displayContent = content ?? ""`; preview, copy, and CodeEditor now use `displayContent`; `ArtifactFilePreview` keeps only `content`/`language`, removing `cleanContent`/`citationMap` and `createCitationMarkdownComponents`.

---

### 10. `frontend/src/components/workspace/messages/message-group.tsx`

```diff
@@ -39,9 +39,7 @@ import { useArtifacts } from "../artifacts";
 import { FlipDisplay } from "../flip-display";
 import { Tooltip } from "../tooltip";

-import { useThread } from "./context";
-
-import { SafeCitationContent } from "./safe-citation-content";
+import { MarkdownContent } from "./markdown-content";

 export function MessageGroup({
```

```diff
@@ -120,7 +118,7 @@ export function MessageGroup({
                 <ChainOfThoughtStep
                   key={step.id}
                   label={
-                    <SafeCitationContent
+                    <MarkdownContent
                       content={step.reasoning ?? ""}
                       isLoading={isLoading}
                       rehypePlugins={rehypePlugins}
@@ -128,12 +126,7 @@ export function MessageGroup({
                   }
                 ></ChainOfThoughtStep>
               ) : (
-                <ToolCall
-                  key={step.id}
-                  {...step}
-                  isLoading={isLoading}
-                  rehypePlugins={rehypePlugins}
-                />
+                <ToolCall key={step.id} {...step} isLoading={isLoading} />
               ),
             )}
           {lastToolCallStep && (
@@ -143,7 +136,6 @@ export function MessageGroup({
                 {...lastToolCallStep}
                 isLast={true}
                 isLoading={isLoading}
-                rehypePlugins={rehypePlugins}
               />
             </FlipDisplay>
           )}
@@ -178,7 +170,7 @@ export function MessageGroup({
               <ChainOfThoughtStep
                 key={lastReasoningStep.id}
                 label={
-                  <SafeCitationContent
+                  <MarkdownContent
                     content={lastReasoningStep.reasoning ?? ""}
                     isLoading={isLoading}
                     rehypePlugins={rehypePlugins}
@@ -201,7 +193,6 @@ function ToolCall({
   result,
   isLast = false,
   isLoading = false,
-  rehypePlugins,
 }: {
   id?: string;
   messageId?: string;
@@ -210,15 +201,10 @@ function ToolCall({
   result?: string | Record<string, unknown>;
   isLast?: boolean;
   isLoading?: boolean;
-  rehypePlugins: ReturnType<typeof useRehypeSplitWordsIntoSpans>;
 }) {
   const { t } = useI18n();
   const { setOpen, autoOpen, autoSelect, selectedArtifact, select } =
     useArtifacts();
-  const { thread } = useThread();
-  const threadIsLoading = thread.isLoading;
-
-  const fileContent = typeof args.content === "string" ? args.content : "";

   if (name === "web_search") {
```

```diff
@@ -364,42 +350,27 @@ function ToolCall({
       }, 100);
     }

-    const isMarkdown =
-      path?.toLowerCase().endsWith(".md") ||
-      path?.toLowerCase().endsWith(".markdown");
-
     return (
-      <>
-        <ChainOfThoughtStep
-          key={id}
-          className="cursor-pointer"
-          label={description}
-          icon={NotebookPenIcon}
-          onClick={() => {
-            select(
-              new URL(
-                `write-file:${path}?message_id=${messageId}&tool_call_id=${id}`,
-              ).toString(),
-            );
-            setOpen(true);
-          }}
-        >
-          {path && (
-            <ChainOfThoughtSearchResult className="cursor-pointer">
-              {path}
-            </ChainOfThoughtSearchResult>
-          )}
-        </ChainOfThoughtStep>
-        {isMarkdown && (
-          <SafeCitationContent
-            content={fileContent}
-            isLoading={threadIsLoading && isLast}
-            rehypePlugins={rehypePlugins}
-            loadingOnly
-            className="mt-2 ml-8"
-          />
-        )}
-      </>
+      <ChainOfThoughtStep
+        key={id}
+        className="cursor-pointer"
+        label={description}
+        icon={NotebookPenIcon}
+        onClick={() => {
+          select(
+            new URL(
+              `write-file:${path}?message_id=${messageId}&tool_call_id=${id}`,
+            ).toString(),
+          );
+          setOpen(true);
+        }}
+      >
+        {path && (
+          <ChainOfThoughtSearchResult className="cursor-pointer">
+            {path}
+          </ChainOfThoughtSearchResult>
+        )}
+      </ChainOfThoughtStep>
     );
   } else if (name === "bash") {
```

- Two occurrences of `SafeCitationContent` -> `MarkdownContent`; ToolCall drops `rehypePlugins` and internal `useThread`/`fileContent`; `write_file` branch removes markdown preview block (`isMarkdown` + `SafeCitationContent`) and keeps only `ChainOfThoughtStep` + path.

---

### 11. `frontend/src/components/workspace/messages/message-list-item.tsx`

```diff
@@ -12,7 +12,6 @@ import {
 } from "@/components/ai-elements/message";
 import { Badge } from "@/components/ui/badge";
 import { resolveArtifactURL } from "@/core/artifacts/utils";
-import { removeAllCitations } from "@/core/citations";
 import {
   extractContentFromMessage,
   extractReasoningContentFromMessage,
@@ -24,7 +23,7 @@ import { humanMessagePlugins } from "@/core/streamdown";
 import { cn } from "@/lib/utils";

 import { CopyButton } from "../copy-button";
-import { SafeCitationContent } from "./safe-citation-content";
+import { MarkdownContent } from "./markdown-content";
 ...
@@ -54,11 +53,11 @@ export function MessageListItem({
       >
         <div className="flex gap-1">
           <CopyButton
-            clipboardData={removeAllCitations(
+            clipboardData={
               extractContentFromMessage(message) ??
               extractReasoningContentFromMessage(message) ??
               ""
-            )}
+            }
           />
         </div>
       </MessageToolbar>
@@ -154,7 +153,7 @@ function MessageContent_({
   return (
     <AIElementMessageContent className={className}>
       {filesList}
-      <SafeCitationContent
+      <MarkdownContent
         content={contentToParse}
         isLoading={isLoading}
         rehypePlugins={[...rehypePlugins, [rehypeKatex, { output: "html" }]]}
```

- Removed `removeAllCitations` and `SafeCitationContent` imports; copy now uses raw content; rendering now uses `MarkdownContent`.

---

### 12. `frontend/src/components/workspace/messages/message-list.tsx`

```diff
@@ -26,7 +26,7 @@ import { StreamingIndicator } from "../streaming-indicator";

 import { MessageGroup } from "./message-group";
 import { MessageListItem } from "./message-list-item";
-import { SafeCitationContent } from "./safe-citation-content";
+import { MarkdownContent } from "./markdown-content";
 import { MessageListSkeleton } from "./skeleton";
 ...
@@ -69,7 +69,7 @@ export function MessageList({
             const message = group.messages[0];
             if (message && hasContent(message)) {
               return (
-                <SafeCitationContent
+                <MarkdownContent
                   key={group.id}
                   content={extractContentFromMessage(message)}
                   isLoading={thread.isLoading}
@@ -89,7 +89,7 @@ export function MessageList({
             return (
               <div className="w-full" key={group.id}>
                 {group.messages[0] && hasContent(group.messages[0]) && (
-                  <SafeCitationContent
+                  <MarkdownContent
                     content={extractContentFromMessage(group.messages[0])}
                     isLoading={thread.isLoading}
                     rehypePlugins={rehypePlugins}
```

- Three places: import and two renders changed from `SafeCitationContent` to `MarkdownContent`, props unchanged.

---

### 13. `frontend/src/components/workspace/messages/subtask-card.tsx`

```diff
@@ -29,7 +29,7 @@ import { cn } from "@/lib/utils";

 import { FlipDisplay } from "../flip-display";

-import { SafeCitationContent } from "./safe-citation-content";
+import { MarkdownContent } from "./markdown-content";
 ...
@@ -153,7 +153,7 @@ export function SubtaskCard({
               <ChainOfThoughtStep
                 label={
                   task.result ? (
-                    <SafeCitationContent
+                    <MarkdownContent
                       content={task.result}
                       isLoading={false}
                       rehypePlugins={rehypePlugins}
```

- Import and one render: `SafeCitationContent` -> `MarkdownContent`.

---

### 14. Added `frontend/src/components/workspace/messages/markdown-content.tsx`

(current workspace addition, not in git)

```ts
"use client";

import type { ImgHTMLAttributes } from "react";
import type { ReactNode } from "react";

import {
  MessageResponse,
  type MessageResponseProps,
} from "@/components/ai-elements/message";
import { streamdownPlugins } from "@/core/streamdown";

export type MarkdownContentProps = {
  content: string;
  isLoading: boolean;
  rehypePlugins: MessageResponseProps["rehypePlugins"];
  className?: string;
  remarkPlugins?: MessageResponseProps["remarkPlugins"];
  isHuman?: boolean;
  img?: (props: ImgHTMLAttributes<HTMLImageElement> & { threadId?: string; maxWidth?: string }) => ReactNode;
};

/** Renders markdown content. */
export function MarkdownContent({
  content,
  rehypePlugins,
  className,
  remarkPlugins = streamdownPlugins.remarkPlugins,
  img,
}: MarkdownContentProps) {
  if (!content) return null;
  const components = img ? { img } : undefined;
  return (
    <MessageResponse
      className={className}
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
    >
      {content}
    </MessageResponse>
  );
}
```

- Pure Markdown rendering component, no citation parsing or loading placeholder logic.

---

### 15. Removed `frontend/src/components/workspace/messages/safe-citation-content.tsx`

- Previously about 85 lines; handled citation parsing, loading, renderBody/loadingOnly, cleanContent/citationMap. Replaced by `MarkdownContent`, file deleted.

---

### 16. Removed `frontend/src/components/ai-elements/inline-citation.tsx`

- Previously about 289 lines; provided `createCitationMarkdownComponents`, used to render `[cite-N]`/URL as clickable citations. Used only by artifact preview and removed, file deleted.

---

## IV. Frontend Core

### 17. Removed `frontend/src/core/citations/index.ts`

- Previously 13 lines exporting `contentWithoutCitationsFromParsed`, `extractDomainFromUrl`, `isExternalUrl`, `parseCitations`, `removeAllCitations`, `shouldShowCitationLoading`, `syntheticCitationFromLink`, `useParsedCitations`, and types `Citation`/`ParseCitationsResult`/`UseParsedCitationsResult`. File deleted.

---

### 18. Removed `frontend/src/core/citations/use-parsed-citations.ts`

- Previously 28 lines; `useParsedCitations(content)` and `UseParsedCitationsResult`. File deleted.

---

### 19. Removed `frontend/src/core/citations/utils.ts`

- Previously 226 lines; parsed `<citations>`/`[cite-N]`, buildCitationMap, removeAllCitations, contentWithoutCitationsFromParsed, etc. File deleted.

---

### 20. `frontend/src/core/i18n/locales/types.ts`

```diff
@@ -115,12 +115,6 @@ export interface Translations {
     startConversation: string;
   };

-  // Citations
-  citations: {
-    loadingCitations: string;
-    loadingCitationsWithCount: (count: number) => string;
-  };
-
   // Chats
   chats: {
```

- Removed `Translations.citations` and its two fields.

---

### 21. `frontend/src/core/i18n/locales/zh-CN.ts`

```diff
@@ -164,12 +164,6 @@ export const zhCN: Translations = {
     startConversation: "Start a new conversation to see messages here",
   },

-  // Citations
-  citations: {
-    loadingCitations: "Organizing citations...",
-    loadingCitationsWithCount: (count: number) => `Organizing ${count} citations...`,
-  },
-
   // Chats
   chats: {
```

- Removed the `citations` namespace.

---

### 22. `frontend/src/core/i18n/locales/en-US.ts`

```diff
@@ -167,13 +167,6 @@ export const enUS: Translations = {
     startConversation: "Start a conversation to see messages here",
   },

-  // Citations
-  citations: {
-    loadingCitations: "Organizing citations...",
-    loadingCitationsWithCount: (count: number) =>
-      `Organizing ${count} citation${count === 1 ? "" : "s"}...`,
-  },
-
   // Chats
   chats: {
```

- Removed the `citations` namespace.

---

## V. Skills and Demo

### 23. `skills/public/github-deep-research/SKILL.md`

```diff
@@ -147,5 +147,5 @@ Save report as: `research_{topic}_{YYYYMMDD}.md`
 3. **Triangulate claims** - 2+ independent sources
 4. **Note conflicting info** - Don't hide contradictions
 5. **Distinguish fact vs opinion** - Label speculation clearly
-6. **Cite inline** - Reference sources near claims
+6. **Reference sources** - Add source references near claims where applicable
 7. **Update as you go** - Don't wait until end to synthesize
```

- Line 150: wording change.

---

### 24. `skills/public/market-analysis/SKILL.md`

```diff
@@ -15,7 +15,7 @@ This skill generates professional, consulting-grade market analysis reports in M
 - Follow the **"Visual Anchor -> Data Contrast -> Integrated Analysis"** flow per sub-chapter
 - Produce insights following the **"Data -> User Psychology -> Strategy Implication"** chain
 - Embed pre-generated charts and construct comparison tables
-- Generate inline citations formatted per **GB/T 7714-2015** standards
+- Include references formatted per **GB/T 7714-2015** where applicable
 - Output reports entirely in Chinese with professional consulting tone
 ...
@@ -36,7 +36,7 @@ The skill expects the following inputs from the upstream agentic workflow:
 | **Analysis Framework Outline** | Defines the logic flow and general topics for the report | Yes |
 | **Data Summary** | The source of truth containing raw numbers and metrics | Yes |
 | **Chart Files** | Local file paths for pre-generated chart images | Yes |
-| **External Search Findings** | URLs and summaries for inline citations | Optional |
+| **External Search Findings** | URLs and summaries for inline references | Optional |
 ...
@@ -87,7 +87,7 @@ The report **MUST NOT** stop after the Conclusion - it **MUST** include Refere
 - **Tone**: McKinsey/BCG - Authoritative, Objective, Professional
 - **Language**: All headings and content strictly in **Chinese**
 - **Number Formatting**: Use English commas for thousands separators (`1,000` not `1.000`)
-- **Data Citation**: **Bold** important viewpoints and key numbers
+- **Data emphasis**: **Bold** important viewpoints and key numbers
 ...
@@ -109,11 +109,9 @@ Every insight must connect **Data -> User Psychology -> Strategy Implication**
    treating male audiences only as a secondary gift-giving segment."
 ```

-### Citations & References
-- **Inline**: Use `[\[Index\]](URL)` format (e.g., `[\[1\]](https://example.com)`)
-- **Placement**: Append citations at the end of sentences using information from External Search Findings
-- **Index Assignment**: Sequential starting from **1** based on order of appearance
-- **References Section**: Formatted strictly per **GB/T 7714-2015**
+### References
+- **Inline**: Use markdown links for sources (e.g. `[Source Title](URL)`) when using External Search Findings
+- **References section**: Formatted strictly per **GB/T 7714-2015**
 ...
@@ -183,7 +181,7 @@ Before considering the report complete, verify:
 - [ ] All headings are in Chinese with proper numbering (no "Chapter/Part/Section")
 - [ ] Charts are embedded with `![Description](path)` syntax
 - [ ] Numbers use English commas for thousands separators
-- [ ] Inline citations use `[\[N\]](URL)` format
+- [ ] Inline references use markdown links where applicable
 - [ ] References section follows GB/T 7714-2015
```

- Multiple places: core capabilities, input table, Data Citation, Citations & References section, and checklist updated to "references" wording and removed the `[\[N\]](URL)` format requirement.

---

### 25. `frontend/public/demo/threads/.../user-data/outputs/research_deerflow_20260201.md`

```diff
@@ -1,12 +1,3 @@
-<citations>
-{"id": "cite-1", "title": "DeerFlow GitHub Repository", "url": "https://github.com/bytedance/deer-flow", "snippet": "..."}
-...(7 JSONL entries total)
-</citations>
 # DeerFlow Deep Research Report

 - **Research Date:** 2026-02-01
```

- Deleted the `<citations>...</citations>` block at the start (9 lines), content now starts at `# DeerFlow Deep Research Report`.

---

### 26. `frontend/public/demo/threads/.../thread.json`

- **Main change**: In a `write_file`'s `args.content`, the original `"<citations>...\n</citations>\n# DeerFlow Deep Research Report\n\n..."` became `"# DeerFlow Deep Research Report\n\n..."`, i.e. remove the `<citations>...</citations>` block while keeping the rest.
- **Other**: One `present_files` `filepaths` changed from a single-line array to multiline format; file ending added/normalized newline.
- Message order, structure, and other fields unchanged.

---

## VI. Statistics

| Item | Count |
|------|------|
| Modified files | 18 |
| Added files | 1 (`markdown-content.tsx`) |
| Deleted files | 5 (`safe-citation-content.tsx`, `inline-citation.tsx`, `core/citations/*` total 3) |
| Total line changes | +62 / -894 (diff stat) |

That is the file-by-file, line-level code change summary.
