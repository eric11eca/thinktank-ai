# File Path Usage Examples

## Three Path Types

Thinktank.ai's file upload system returns three different paths. Each path is used for a different scenario.

### 1. Physical filesystem path (`path`)

```
.think-tank/threads/{thread_id}/user-data/uploads/document.pdf
```

**Purpose:**
- Actual file location on the server filesystem
- Relative to the `backend/` directory
- Used for direct filesystem access, backups, debugging, etc.

**Example:**
```python
# Direct access in Python code
from pathlib import Path
file_path = Path("backend/.think-tank/threads/abc123/user-data/uploads/document.pdf")
content = file_path.read_bytes()
```

### 2. Virtual path (`virtual_path`)

```
/mnt/user-data/uploads/document.pdf
```

**Purpose:**
- Path used by the Agent inside the sandbox environment
- Sandbox automatically maps to the physical path
- All Agent file operation tools use this path

**Example:**
Agent usage in conversation:
```python
# Agent uses read_file tool
read_file(path="/mnt/user-data/uploads/document.pdf")

# Agent uses bash tool
bash(command="cat /mnt/user-data/uploads/document.pdf")
```

### 3. HTTP access URL (`artifact_url`)

```
/api/threads/{thread_id}/artifacts/mnt/user-data/uploads/document.pdf
```

**Purpose:**
- Frontend accesses files over HTTP
- Used for downloading and previewing files
- Can be opened directly in a browser

**Example:**
```typescript
// Frontend TypeScript/JavaScript code
const threadId = "abc123";
const filename = "document.pdf";

// Download file
const downloadUrl = `/api/threads/${threadId}/artifacts/mnt/user-data/uploads/${filename}?download=true`;
window.open(downloadUrl);

// Preview in a new window
const viewUrl = `/api/threads/${threadId}/artifacts/mnt/user-data/uploads/${filename}`;
window.open(viewUrl, "_blank");

// Fetch via API
const response = await fetch(viewUrl);
const blob = await response.blob();
```

## End-to-End Flow Example

### Scenario: Frontend uploads a file and asks the Agent to process it

```typescript
// 1. Frontend uploads a file
async function uploadAndProcess(threadId: string, file: File) {
  // Upload file
  const formData = new FormData();
  formData.append("files", file);

  const uploadResponse = await fetch(`/api/threads/${threadId}/uploads`, {
    method: "POST",
    body: formData,
  });

  const uploadData = await uploadResponse.json();
  const fileInfo = uploadData.files[0];

  console.log("File info:", fileInfo);
  // {
  //   filename: "report.pdf",
  //   path: ".think-tank/threads/abc123/user-data/uploads/report.pdf",
  //   virtual_path: "/mnt/user-data/uploads/report.pdf",
  //   artifact_url: "/api/threads/abc123/artifacts/mnt/user-data/uploads/report.pdf",
  //   markdown_file: "report.md",
  //   markdown_path: ".think-tank/threads/abc123/user-data/uploads/report.md",
  //   markdown_virtual_path: "/mnt/user-data/uploads/report.md",
  //   markdown_artifact_url: "/api/threads/abc123/artifacts/mnt/user-data/uploads/report.md"
  // }

  // 2. Send a message to the Agent
  await sendMessage(threadId, "Please analyze the PDF I just uploaded.");

  // The Agent will automatically see the file list, including:
  // - report.pdf (virtual path: /mnt/user-data/uploads/report.pdf)
  // - report.md (virtual path: /mnt/user-data/uploads/report.md)

  // 3. Frontend can directly access the converted Markdown
  const mdResponse = await fetch(fileInfo.markdown_artifact_url);
  const markdownContent = await mdResponse.text();
  console.log("Markdown content:", markdownContent);

  // 4. Or download the original PDF
  const downloadLink = document.createElement("a");
  downloadLink.href = fileInfo.artifact_url + "?download=true";
  downloadLink.download = fileInfo.filename;
  downloadLink.click();
}
```

## Path Mapping Table

| Scenario | Path type | Example |
|----------|-----------|---------|
| Backend server code access | `path` | `.think-tank/threads/abc123/user-data/uploads/file.pdf` |
| Agent tool call | `virtual_path` | `/mnt/user-data/uploads/file.pdf` |
| Frontend download/preview | `artifact_url` | `/api/threads/abc123/artifacts/mnt/user-data/uploads/file.pdf` |
| Backup script | `path` | `.think-tank/threads/abc123/user-data/uploads/file.pdf` |
| Logging | `path` | `.think-tank/threads/abc123/user-data/uploads/file.pdf` |

## Code Examples

### Python - backend processing

```python
from pathlib import Path
from src.agents.middlewares.thread_data_middleware import THREAD_DATA_BASE_DIR

def process_uploaded_file(thread_id: str, filename: str):
    # Use the physical path
    base_dir = Path.cwd() / THREAD_DATA_BASE_DIR / thread_id / "user-data" / "uploads"
    file_path = base_dir / filename

    # Read directly
    with open(file_path, "rb") as f:
        content = f.read()

    return content
```

### JavaScript - frontend access

```javascript
// List uploaded files
async function listUploadedFiles(threadId) {
  const response = await fetch(`/api/threads/${threadId}/uploads/list`);
  const data = await response.json();

  // Create download links for each file
  data.files.forEach((file) => {
    console.log(`File: ${file.filename}`);
    console.log(`Download: ${file.artifact_url}?download=true`);
    console.log(`Preview: ${file.artifact_url}`);

    // If it's a document, there is also a Markdown version
    if (file.markdown_artifact_url) {
      console.log(`Markdown: ${file.markdown_artifact_url}`);
    }
  });

  return data.files;
}

// Delete file
async function deleteFile(threadId, filename) {
  const response = await fetch(`/api/threads/${threadId}/uploads/${filename}`, {
    method: "DELETE",
  });
  return response.json();
}
```

### React component example

```tsx
import React, { useState, useEffect } from "react";

interface UploadedFile {
  filename: string;
  size: number;
  path: string;
  virtual_path: string;
  artifact_url: string;
  extension: string;
  modified: number;
  markdown_artifact_url?: string;
}

function FileUploadList({ threadId }: { threadId: string }) {
  const [files, setFiles] = useState<UploadedFile[]>([]);

  useEffect(() => {
    fetchFiles();
  }, [threadId]);

  async function fetchFiles() {
    const response = await fetch(`/api/threads/${threadId}/uploads/list`);
    const data = await response.json();
    setFiles(data.files);
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const fileList = event.target.files;
    if (!fileList) return;

    const formData = new FormData();
    Array.from(fileList).forEach((file) => {
      formData.append("files", file);
    });

    await fetch(`/api/threads/${threadId}/uploads`, {
      method: "POST",
      body: formData,
    });

    fetchFiles(); // Refresh list
  }

  async function handleDelete(filename: string) {
    await fetch(`/api/threads/${threadId}/uploads/${filename}`, {
      method: "DELETE",
    });
    fetchFiles(); // Refresh list
  }

  return (
    <div>
      <input type="file" multiple onChange={handleUpload} />

      <ul>
        {files.map((file) => (
          <li key={file.filename}>
            <span>{file.filename}</span>
            <a href={file.artifact_url} target="_blank">Preview</a>
            <a href={`${file.artifact_url}?download=true`}>Download</a>
            {file.markdown_artifact_url && (
              <a href={file.markdown_artifact_url} target="_blank">Markdown</a>
            )}
            <button onClick={() => handleDelete(file.filename)}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

## Notes

1. **Path safety**
   - Physical paths (`path`) include the thread ID to ensure isolation
   - API validates paths to prevent directory traversal attacks
   - Frontend should not use `path` directly; use `artifact_url`

2. **Agent usage**
   - The Agent only sees and uses `virtual_path`
   - Sandbox maps virtual paths to physical paths automatically
   - The Agent does not need to know the actual filesystem layout

3. **Frontend integration**
   - Always use `artifact_url` to access files
   - Do not attempt direct filesystem access
   - Use `?download=true` to force download

4. **Markdown conversion**
   - On successful conversion, extra `markdown_*` fields are returned
   - Prefer the Markdown version when possible (easier to process)
   - Original files are always preserved
