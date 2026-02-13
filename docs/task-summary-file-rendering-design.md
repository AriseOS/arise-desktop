# Task Summary & File Rendering Design

## 1. Overview

This document describes the design for enhancing task summary display with rich file attachment rendering in Ami, based on research of Eigent's implementation patterns.

## 2. Current State Analysis

### 2.1 Eigent's Approach

Based on thorough research of the Eigent codebase:

**Task Summary Display:**
- Uses `SummaryMarkDown.tsx` component with custom emerald-green styling
- Supports typewriter effect for streaming display
- Detects HTML documents and renders in styled `<pre>` blocks
- Uses `ReactMarkdown` with custom component styling (h1, h2, lists, code blocks)

**File Attachments:**
- Simple pill-shaped cards with `FileText` icon
- Displays filename split into name + extension
- **Click action**: `window.ipcRenderer.invoke('reveal-in-folder', file.filePath)` - opens system file explorer
- No inline preview/thumbnail - metadata only
- Files collected via `WRITE_FILE` SSE events during execution

**Key Files in Eigent:**
```
src/components/ChatBox/MessageItem/
├── SummaryMarkDown.tsx     # Summary with custom styling
├── AgentMessageCard.tsx    # Displays attaches array
└── MarkDown.tsx           # Image handling (relative path -> data URL)
```

**SSE Event Structure:**
```typescript
// WRITE_FILE event
{
  step: "write_file",
  data: {
    file_path: "/path/to/file.html",
    process_task_id: "task-123"
  }
}

// END event (with file list)
{
  step: "end",
  data: {
    summary: "...",
    fileList: [{ name, type, path, icon }]
  }
}
```

### 2.2 Ami's Current State

**Backend:**
- `WriteFileData` event exists with `file_path`, `file_name`, `file_size`, `content_preview`, `mime_type`
- `WaitConfirmData` sends summary text but **no file attachments**
- `_aggregate_ami_results()` generates summary via `TaskSummaryAgent`
- `fileList` tracked in task state but not sent with summary

**Frontend:**
- `AgentMessage.jsx` renders Markdown via `ReactMarkdown`
- `attaches` array support exists but rarely populated
- `FilePreview.jsx` supports images, syntax highlighting for code
- `FileBrowser.jsx` shows file tree in Workspace tab
- `write_file` event adds files to `chatStore.fileList`

**Gap Analysis:**
| Feature | Eigent | Ami | Gap |
|---------|--------|-----|-----|
| Markdown rendering | Yes | Yes | None |
| File cards in summary | Yes | Partial | Need to attach files to summary message |
| Click to reveal in folder | Yes (Electron) | No | Need Tauri equivalent |
| Image inline preview | Yes | No | Need to implement |
| HTML preview | Pre-formatted | No | Need iframe sandbox |
| PDF preview | No | No | Optional enhancement |

## 3. Proposed Design

### 3.1 Design Philosophy

**Hybrid Mode**: Previewable content renders inline, non-previewable shows file cards with click-to-open.

```
┌─────────────────────────────────────────────────────────────┐
│ Task Summary (Markdown)                                      │
│                                                             │
│ ## Results                                                  │
│ Created 3 files for your analysis:                          │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📊 report.html                    [Preview] [Open ↗]   │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │          <Rendered HTML in sandbox>               │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📄 data.csv                       [Preview] [Open ↗]   │ │
│ │ ┌───────────────────────────────────────────────────┐   │ │
│ │ │ Name     │ Value │ Date                           │   │ │
│ │ │ Item 1   │ 100   │ 2026-02-03                     │   │ │
│ │ │ ... (5 of 100 rows)                               │   │ │
│ │ └───────────────────────────────────────────────────┘   │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📁 /Users/.../output/                      [Open ↗]    │ │
│ │    5 files, 2.3 MB total                               │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📑 presentation.pptx                       [Open ↗]    │ │
│ │    PowerPoint, 1.2 MB                                  │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 File Type Rendering Strategy

| File Type | Extension | Render Mode | Preview Content |
|-----------|-----------|-------------|-----------------|
| **Images** | png, jpg, gif, webp, svg | Inline thumbnail | Click to enlarge |
| **HTML** | html, htm | Iframe sandbox | Full render |
| **CSV** | csv | Table preview | First 5 rows |
| **Excel** | xlsx, xls | Table preview | First sheet, 5 rows |
| **Code** | py, js, json, md, txt | Syntax highlight | First 20 lines |
| **PDF** | pdf | Thumbnail + page count | Click to open |
| **Office** | docx, pptx | File card only | Click to open |
| **Folder** | (directory) | File list summary | Click to reveal |
| **Other** | * | File card only | Click to open |

### 3.3 Data Flow Changes

#### 3.3.1 Backend: Attach Files to Summary

**Modify `WaitConfirmData` in `action_types.py`:**

```python
class WaitConfirmData(BaseActionData):
    """Wait for user confirmation with simple answer (Eigent pattern)."""

    action: Literal[Action.wait_confirm] = Action.wait_confirm
    content: str
    question: str
    context: str = "initial"
    # NEW: Attach files created during task execution
    attachments: Optional[List[FileAttachment]] = None


class FileAttachment(BaseModel):
    """File attachment metadata for summary display."""

    file_name: str
    file_path: str
    file_type: str  # "image" | "html" | "csv" | "excel" | "code" | "pdf" | "office" | "folder" | "other"
    mime_type: Optional[str] = None
    file_size: Optional[int] = None

    # Preview data (optional, based on file_type)
    preview: Optional[FilePreview] = None


class FilePreview(BaseModel):
    """Preview content for file attachment."""

    # For images: base64 thumbnail
    thumbnail: Optional[str] = None

    # For CSV/Excel: first N rows as list of lists
    table_preview: Optional[List[List[str]]] = None
    table_total_rows: Optional[int] = None

    # For code/text: first N lines
    text_preview: Optional[str] = None
    text_total_lines: Optional[int] = None

    # For folders: file list summary
    folder_files: Optional[List[str]] = None
    folder_total_size: Optional[int] = None

    # For PDF: page count
    pdf_page_count: Optional[int] = None
```

**Modify `_aggregate_ami_results()` in `quick_task_service.py`:**

```python
async def _aggregate_ami_results(self, task_id, state, subtasks, result, duration):
    """Aggregate task results with file attachments."""

    # ... existing summary generation code ...

    # Collect files created during execution
    attachments = await self._collect_task_files(task_id, state)

    # Store attachments in state for WaitConfirmData
    state.attachments = attachments

    return summary_output


async def _collect_task_files(self, task_id: str, state: TaskState) -> List[FileAttachment]:
    """Collect and prepare file attachments from task execution."""

    attachments = []
    workspace_dir = Path(state.working_directory)

    # Get files from state.files (populated by write_file events)
    for file_info in state.files:
        file_path = Path(file_info.get("path", ""))
        if not file_path.exists():
            continue

        attachment = await self._create_file_attachment(file_path)
        if attachment:
            attachments.append(attachment)

    return attachments


async def _create_file_attachment(self, file_path: Path) -> Optional[FileAttachment]:
    """Create FileAttachment with preview data based on file type."""

    suffix = file_path.suffix.lower()
    file_type = self._detect_file_type(suffix)

    attachment = FileAttachment(
        file_name=file_path.name,
        file_path=str(file_path),
        file_type=file_type,
        mime_type=mimetypes.guess_type(str(file_path))[0],
        file_size=file_path.stat().st_size,
    )

    # Generate preview based on type
    if file_type == "image":
        attachment.preview = await self._generate_image_preview(file_path)
    elif file_type == "csv":
        attachment.preview = await self._generate_csv_preview(file_path)
    elif file_type == "html":
        attachment.preview = FilePreview()  # HTML renders directly
    elif file_type == "code":
        attachment.preview = await self._generate_code_preview(file_path)
    # ... etc

    return attachment
```

**Send attachments with WaitConfirmData:**

```python
# In _execute_task_ami(), after aggregation:
await state.put_event(WaitConfirmData(
    task_id=task_id,
    content=final_output,
    question=task_to_decompose,
    context=context,
    attachments=state.attachments,  # NEW
))
```

#### 3.3.2 Frontend: Enhanced Message Rendering

**Update `AgentMessage.jsx`:**

```jsx
import FileAttachmentCard from './FileAttachmentCard';

function AgentMessage({ message }) {
  const { content, timestamp, step, attaches, attachments } = message;

  // Use new attachments field, fallback to legacy attaches
  const files = attachments || attaches || [];

  return (
    <div className={`agent-message ${getMessageClass()}`}>
      {/* Header */}
      <div className="message-header">...</div>

      {/* Content - Markdown */}
      <div className="message-content">
        {content && (
          <div className="message-text markdown-content">
            <ReactMarkdown>{content}</ReactMarkdown>
          </div>
        )}

        {/* File Attachments */}
        {files.length > 0 && (
          <div className="message-attachments">
            {files.map((file, index) => (
              <FileAttachmentCard
                key={`file-${index}`}
                file={file}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

**Create `FileAttachmentCard.jsx`:**

```jsx
import { useState } from 'react';
import { invoke } from '@tauri-apps/api/tauri';
import Icon from '../Icons';
import ImagePreview from './previews/ImagePreview';
import HtmlPreview from './previews/HtmlPreview';
import TablePreview from './previews/TablePreview';
import CodePreview from './previews/CodePreview';

function FileAttachmentCard({ file }) {
  const [expanded, setExpanded] = useState(false);
  const [enlargedImage, setEnlargedImage] = useState(null);

  const {
    file_name,
    file_path,
    file_type,
    file_size,
    preview,
  } = file;

  // Open file in system default app
  const handleOpen = async () => {
    try {
      await invoke('open_path', { path: file_path });
    } catch (e) {
      console.error('Failed to open file:', e);
    }
  };

  // Reveal in Finder/Explorer
  const handleReveal = async () => {
    try {
      await invoke('reveal_in_folder', { path: file_path });
    } catch (e) {
      console.error('Failed to reveal in folder:', e);
    }
  };

  // Render preview based on file type
  const renderPreview = () => {
    if (!expanded && !isAlwaysExpanded(file_type)) return null;

    switch (file_type) {
      case 'image':
        return (
          <ImagePreview
            src={preview?.thumbnail || file_path}
            onClick={() => setEnlargedImage(file_path)}
          />
        );
      case 'html':
        return <HtmlPreview filePath={file_path} />;
      case 'csv':
      case 'excel':
        return (
          <TablePreview
            rows={preview?.table_preview}
            totalRows={preview?.table_total_rows}
          />
        );
      case 'code':
        return (
          <CodePreview
            content={preview?.text_preview}
            totalLines={preview?.text_total_lines}
            language={getLanguageFromExt(file_name)}
          />
        );
      case 'folder':
        return (
          <FolderPreview
            files={preview?.folder_files}
            totalSize={preview?.folder_total_size}
          />
        );
      default:
        return null;
    }
  };

  // Determine if preview should always show
  const isAlwaysExpanded = (type) => ['image'].includes(type);
  const hasPreview = ['image', 'html', 'csv', 'excel', 'code', 'folder'].includes(file_type);

  return (
    <div className={`file-attachment-card file-type-${file_type}`}>
      {/* Header */}
      <div className="file-card-header">
        <Icon name={getIconForType(file_type)} size={20} />
        <div className="file-info">
          <span className="file-name">{file_name}</span>
          {file_size && (
            <span className="file-size">{formatFileSize(file_size)}</span>
          )}
        </div>
        <div className="file-actions">
          {hasPreview && !isAlwaysExpanded(file_type) && (
            <button
              className="action-btn preview"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? 'Hide' : 'Preview'}
            </button>
          )}
          <button className="action-btn open" onClick={handleOpen}>
            Open ↗
          </button>
        </div>
      </div>

      {/* Preview */}
      {renderPreview()}

      {/* Image enlargement modal */}
      {enlargedImage && (
        <ImageModal
          src={enlargedImage}
          onClose={() => setEnlargedImage(null)}
        />
      )}
    </div>
  );
}
```

#### 3.3.3 Tauri Backend: File Operations

**Add commands in `src-tauri/src/main.rs`:**

```rust
#[tauri::command]
async fn open_path(path: String) -> Result<(), String> {
    open::that(&path).map_err(|e| e.to_string())
}

#[tauri::command]
async fn reveal_in_folder(path: String) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .args(["-R", &path])
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .args(["/select,", &path])
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    #[cfg(target_os = "linux")]
    {
        // Use xdg-open for the parent directory
        let parent = std::path::Path::new(&path)
            .parent()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or(path);
        std::process::Command::new("xdg-open")
            .arg(&parent)
            .spawn()
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}
```

### 3.4 Preview Components

#### 3.4.1 HTML Preview (Sandbox Iframe)

```jsx
// components/ChatBox/MessageItem/previews/HtmlPreview.jsx

function HtmlPreview({ filePath, maxHeight = 400 }) {
  const [content, setContent] = useState('');
  const iframeRef = useRef(null);

  useEffect(() => {
    loadHtmlContent(filePath).then(setContent);
  }, [filePath]);

  return (
    <div className="html-preview" style={{ maxHeight }}>
      <iframe
        ref={iframeRef}
        srcDoc={content}
        sandbox="allow-same-origin"  // No scripts allowed
        title="HTML Preview"
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
          background: 'white',
        }}
      />
    </div>
  );
}
```

#### 3.4.2 Table Preview (CSV/Excel)

```jsx
// components/ChatBox/MessageItem/previews/TablePreview.jsx

function TablePreview({ rows, totalRows, maxRows = 5 }) {
  if (!rows || rows.length === 0) return null;

  const headers = rows[0];
  const dataRows = rows.slice(1, maxRows + 1);
  const remaining = totalRows - maxRows - 1;

  return (
    <div className="table-preview">
      <table>
        <thead>
          <tr>
            {headers.map((h, i) => <th key={i}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {dataRows.map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => <td key={j}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      {remaining > 0 && (
        <div className="preview-footer">
          ... {remaining} more rows
        </div>
      )}
    </div>
  );
}
```

#### 3.4.3 Image Preview with Enlarge

```jsx
// components/ChatBox/MessageItem/previews/ImagePreview.jsx

function ImagePreview({ src, alt = 'Preview', onClick }) {
  const [loaded, setLoaded] = useState(false);

  return (
    <div className="image-preview" onClick={onClick}>
      {!loaded && <div className="image-loading">Loading...</div>}
      <img
        src={src.startsWith('data:') ? src : `file://${src}`}
        alt={alt}
        onLoad={() => setLoaded(true)}
        style={{
          maxHeight: 200,
          maxWidth: '100%',
          objectFit: 'contain',
          cursor: 'pointer',
          display: loaded ? 'block' : 'none',
        }}
      />
    </div>
  );
}

function ImageModal({ src, onClose }) {
  return (
    <div className="image-modal-overlay" onClick={onClose}>
      <div className="image-modal-content">
        <img src={src} alt="Full size" />
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
    </div>
  );
}
```

## 4. Implementation Plan

### Phase 1: Basic File Cards (1-2 days)
1. Add `attachments` field to `WaitConfirmData`
2. Collect files in `_aggregate_ami_results()`
3. Create `FileAttachmentCard` component (no preview)
4. Add Tauri `open_path` and `reveal_in_folder` commands

### Phase 2: Image Preview (1 day)
1. Generate image thumbnails (base64) in backend
2. Create `ImagePreview` component with enlarge modal
3. Support both local paths and data URLs

### Phase 3: HTML Preview (1 day)
1. Create `HtmlPreview` with sandboxed iframe
2. Handle relative resource paths (CSS, images)

### Phase 4: Table Preview (1-2 days)
1. Add CSV/Excel preview generation in backend
2. Create `TablePreview` component
3. Handle encoding issues (UTF-8, GBK, etc.)

### Phase 5: Code Preview (1 day)
1. Add text file preview extraction
2. Create `CodePreview` with syntax highlighting
3. Support common languages

### Phase 6: Polish (1 day)
1. Folder summary display
2. Loading states and error handling
3. Styling and animations
4. Mobile responsiveness

## 5. File Structure

```
src/clients/desktop_app/
├── ami_daemon/
│   ├── base_agent/events/
│   │   └── action_types.py        # Add FileAttachment, modify WaitConfirmData
│   └── services/
│       └── quick_task_service.py  # Add file collection logic
├── src/
│   └── components/
│       └── ChatBox/
│           └── MessageItem/
│               ├── AgentMessage.jsx        # Update to use FileAttachmentCard
│               ├── FileAttachmentCard.jsx  # NEW: Main file card component
│               └── previews/
│                   ├── ImagePreview.jsx    # NEW
│                   ├── HtmlPreview.jsx     # NEW
│                   ├── TablePreview.jsx    # NEW
│                   ├── CodePreview.jsx     # NEW
│                   └── FolderPreview.jsx   # NEW
└── src-tauri/
    └── src/
        └── main.rs                # Add open_path, reveal_in_folder

```

## 6. Comparison with Eigent

| Aspect | Eigent | Ami (Proposed) |
|--------|--------|----------------|
| File display | Simple cards | Rich cards with inline preview |
| Image preview | Data URL conversion | Thumbnail + enlarge modal |
| HTML preview | Pre-formatted text | Sandboxed iframe render |
| CSV/Excel | None | Table preview |
| Click action | Reveal in folder (Electron) | Open file + Reveal (Tauri) |
| Preview toggle | No | Yes (expand/collapse) |

## 7. Security Considerations

1. **HTML Sandbox**: Use `sandbox="allow-same-origin"` - no scripts
2. **File Path Validation**: Validate paths are within workspace
3. **Size Limits**: Limit preview generation for large files
4. **MIME Type Checking**: Verify file type matches extension

## 8. Performance Considerations

1. **Lazy Preview Generation**: Generate on-demand, not for all files
2. **Thumbnail Caching**: Cache generated thumbnails
3. **Pagination**: For large tables, show first N rows only
4. **Async Loading**: Load previews asynchronously
