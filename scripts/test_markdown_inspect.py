"""Generate comprehensive DOCX+PDF test files for visual inspection.

Output: scripts/test_output/ with matched .docx and .pdf pairs.
"""

import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.clients.desktop_app.ami_daemon.base_agent.tools.toolkits.file_toolkit import (
    FileToolkit,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "test_output")


FULL_MARKDOWN = """\
# Main Title

## 1. Text Formatting

This paragraph has **bold text**, *italic text*, and `inline code`.
Here is a [link example](https://example.com) and some ***bold italic*** text.

## 2. Lists

### Unordered List
- First bullet
- Second bullet
- Third bullet with **bold**

### Ordered List
1. Step one
2. Step two
3. Step three with *emphasis*

## 3. Table

| Name   | Age | City     |
|--------|-----|----------|
| Alice  | 28  | Beijing  |
| Bob    | 35  | Shanghai |
| Charlie| 42  | Tokyo    |

## 4. Code Block

```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

print(fibonacci(10))  # Output: 55
```

## 5. Blockquote

> "The best way to predict the future is to invent it."
> — Alan Kay

## 6. Horizontal Rule

Some text above the rule.

---

Some text below the rule.

## 7. CJK Characters

### Chinese
这是一段中文测试文字。人工智能正在改变世界。

### Japanese
これは日本語のテスト文です。人工知能が世界を変えています。

### Korean
이것은 한국어 테스트 문장입니다.

## 8. Mixed Content

The following table contains **formatted** text and `code`:

| Feature    | Status   | Notes              |
|------------|----------|--------------------|
| **Bold**   | Done     | Works in tables    |
| *Italic*   | Done     | Also works         |
| `Code`     | Done     | Inline code works  |

### Summary List
1. All formatting elements are tested
2. CJK support is verified
3. Tables render correctly
"""

CJK_HEAVY = """\
# 产品需求文档

## 一、项目概述

本文档描述了 **AMI 智能助手**的核心功能需求。该产品旨在为用户提供*高效*、`智能`的任务自动化服务。

## 二、功能列表

### 2.1 浏览器自动化
- 网页搜索与信息提取
- 表单自动填写
- 多标签页管理

### 2.2 文档处理
1. Word 文档生成
2. PDF 报告导出
3. Excel 数据分析

## 三、技术规格

| 模块 | 技术栈 | 状态 |
|------|--------|------|
| 前端 | Tauri + React | 开发中 |
| 后端 | Python + FastAPI | 已完成 |
| AI引擎 | Claude API | 已集成 |

## 四、备注

> 所有模块需要支持国际化，包括中文、日文、韩文的正确显示。

```json
{
    "project": "AMI",
    "version": "2.0",
    "language": "多语言支持"
}
```
"""

SPECIAL_CHARS = """\
# Special Characters Test

## HTML Entities
Text with < less than, > greater than, & ampersand.

Quotes: "double" and 'single'.

## Code with Special Chars
```
if (x < 10 && y > 20) {
    console.log("Hello & World");
}
```

## Symbols
Price: $99.99 | Discount: 20% | Rating: 4.5/5.0
Math: 2 + 2 = 4, 10 - 3 = 7, 5 * 6 = 30
"""


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Clean old output
    for f in os.listdir(OUTPUT_DIR):
        os.remove(os.path.join(OUTPUT_DIR, f))

    tk = FileToolkit(working_directory=OUTPUT_DIR, backup_enabled=False)

    test_cases = [
        ("01_full_test", "Comprehensive Formatting Test", FULL_MARKDOWN),
        ("02_cjk_heavy", "产品需求文档", CJK_HEAVY),
        ("03_special_chars", "Special Characters", SPECIAL_CHARS),
    ]

    for name, title, content in test_cases:
        for ext in (".docx", ".pdf"):
            filename = f"{name}{ext}"
            result = tk.write_to_file(title, content, filename)
            status = "OK" if "successfully" in result else "FAIL"
            size = os.path.getsize(os.path.join(OUTPUT_DIR, filename)) if status == "OK" else 0
            print(f"  {filename:40s}  {status}  ({size:,} bytes)")

    print(f"\nAll files written to: {OUTPUT_DIR}")
    print("Please inspect the .docx and .pdf files to verify formatting.")


if __name__ == "__main__":
    main()
