"""Test script: verify Markdown → DOCX and Markdown → PDF conversion.

Creates both .docx and .pdf from the same Markdown content and prints
status. Manually inspect the output files to verify formatting.
"""

import sys
import os
import tempfile

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.file_toolkit import (
    FileToolkit,
)

MARKDOWN_CONTENT = """\
# Title
## Section 1
This is **bold** and *italic* and `code`.

### Subsection 1.1
A normal paragraph with some text.

- Bullet 1
- Bullet 2
- Bullet 3

1. Numbered 1
2. Numbered 2
3. Numbered 3

| Col A | Col B | Col C |
|-------|-------|-------|
| 1     | 2     | 3     |
| 4     | 5     | 6     |

```python
def hello():
    print("Hello, world!")
```

> This is a blockquote with important information.

---

## Section 2: CJK Support
This section tests Chinese characters: 你好世界，这是一个测试文档。
日本語テスト：こんにちは世界。
한국어 테스트: 안녕하세요 세계.
"""


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        toolkit = FileToolkit(working_directory=tmpdir, backup_enabled=False)

        # Test DOCX
        print("=== Testing DOCX generation ===")
        result_docx = toolkit.write_to_file(
            title="Markdown Test Document",
            content=MARKDOWN_CONTENT,
            filename="test_output.docx",
        )
        print(f"DOCX result: {result_docx}")

        docx_path = os.path.join(tmpdir, "test_output.docx")
        if os.path.exists(docx_path):
            size = os.path.getsize(docx_path)
            print(f"DOCX size: {size} bytes")
            assert size > 0, "DOCX file is empty"
            print("DOCX: OK")
        else:
            print("DOCX: FAILED - file not created")
            return 1

        # Test PDF
        print("\n=== Testing PDF generation ===")
        result_pdf = toolkit.write_to_file(
            title="Markdown Test Document",
            content=MARKDOWN_CONTENT,
            filename="test_output.pdf",
        )
        print(f"PDF result: {result_pdf}")

        pdf_path = os.path.join(tmpdir, "test_output.pdf")
        if os.path.exists(pdf_path):
            size = os.path.getsize(pdf_path)
            print(f"PDF size: {size} bytes")
            assert size > 0, "PDF file is empty"
            print("PDF: OK")
        else:
            print("PDF: FAILED - file not created")
            return 1

        # Copy outputs to a visible location for manual inspection
        import shutil
        output_dir = os.path.join(os.path.dirname(__file__), "test_output")
        os.makedirs(output_dir, exist_ok=True)
        shutil.copy2(docx_path, os.path.join(output_dir, "test_output.docx"))
        shutil.copy2(pdf_path, os.path.join(output_dir, "test_output.pdf"))
        print(f"\nOutput files copied to: {output_dir}")

    print("\nAll tests passed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
