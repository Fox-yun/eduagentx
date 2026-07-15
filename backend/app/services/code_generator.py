"""Deterministic code project ZIP generator with security checks.

Generates ZIP archives containing code examples, README, and setup files
from unit content WITHOUT using LLM. Enforces security restrictions.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any

import structlog

logger = structlog.get_logger()


class CodeZIPGenerator:
    """Deterministic code project ZIP generator."""

    # Security: forbidden patterns in generated code
    _FORBIDDEN_PATTERNS = [
        "rm -rf /",
        "rm -rf",
        "sudo rm",
        ":(){:|:&};:",  # fork bomb
        "wget ",
        "curl ",
        "eval(",
        "exec(",
        "__import__",
        "system(",
        "subprocess.call",
        "subprocess.run",
    ]

    # Security: forbidden file extensions
    _FORBIDDEN_EXTENSIONS = {
        ".sh",
        ".bat",
        ".cmd",
        ".ps1",
        ".app",
        ".exe",
        ".dll",
        ".dylib",
        ".so",
    }

    # Security: max file size per file
    _MAX_FILE_SIZE = 100_000  # 100 KB

    # Security: max total ZIP size
    _MAX_ZIP_SIZE = 500_000  # 500 KB

    @classmethod
    def generate_zip_bytes(
        cls,
        unit_content: dict[str, Any],
    ) -> tuple[bytes, list[str]]:
        """Generate ZIP file bytes from unit content.

        Args:
            unit_content: Dictionary containing unit content

        Returns:
            Tuple of (ZIP bytes, list of file names)

        Raises:
            RuntimeError: If security checks fail or generation fails
        """
        try:
            zip_buffer = BytesIO()

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                files = []

                # Add README.md
                readme_content = cls._generate_readme(unit_content)
                zf.writestr("README.md", readme_content)
                files.append("README.md")

                # Add example files based on unit content
                example_files = cls._generate_example_files(unit_content)
                for filename, content in example_files:
                    # Security check: file extension
                    if any(filename.lower().endswith(ext) for ext in cls._FORBIDDEN_EXTENSIONS):
                        logger.warning("forbidden_file_extension_skipped", filename=filename)
                        continue

                    # Security check: file size
                    if len(content) > cls._MAX_FILE_SIZE:
                        content = content[: cls._MAX_FILE_SIZE]
                        logger.warning("file_size_limited", filename=filename, max_size=cls._MAX_FILE_SIZE)

                    # Security check: forbidden patterns
                    if cls._contains_forbidden_patterns(content):
                        logger.warning("forbidden_patterns_found_skipped", filename=filename)
                        continue

                    zf.writestr(filename, content)
                    files.append(filename)

            # Security check: total ZIP size
            zip_bytes = zip_buffer.getvalue()
            if len(zip_bytes) > cls._MAX_ZIP_SIZE:
                raise RuntimeError(f"Generated ZIP too large: {len(zip_bytes)} bytes")

            return zip_bytes, files

        except Exception as e:
            logger.error("code_zip_generation_failed", error=str(e))
            raise RuntimeError(f"Code ZIP generation failed: {e}") from e

    @classmethod
    def _contains_forbidden_patterns(cls, content: str) -> bool:
        """Check if content contains forbidden security patterns."""
        content_lower = content.lower()
        return any(pattern.lower() in content_lower for pattern in cls._FORBIDDEN_PATTERNS)

    @classmethod
    def _generate_readme(cls, unit_content: dict[str, Any]) -> str:
        """Generate README.md content."""
        intro = unit_content.get("introduction", "").strip("# \n")
        title = intro.split("\n")[0] if intro else "Code Example Project"
        objectives = unit_content.get("objectives", [])
        sections = unit_content.get("sections", [])
        practice_tasks = unit_content.get("practice_tasks", [])
        summary = unit_content.get("summary", "")

        readme_lines = [
            f"# {title}\n",
            "这是一个自动生成的代码示例项目，用于辅助学习。\n",
            "## 学习目标\n",
        ]

        for obj in objectives:
            readme_lines.append(f"- {obj}")

        readme_lines.extend([
            "\n## 目录说明\n",
            "- README.md: 项目说明文件\n",
        ])

        if sections:
            readme_lines.extend([
                "\n## 知识点说明\n",
                "本示例涵盖以下核心知识点：\n",
            ])
            for i, sec in enumerate(sections[:3], 1):
                sec_title = sec.get("title", f"章节 {i}")
                readme_lines.append(f"{i}. {sec_title}")

        if practice_tasks:
            readme_lines.extend([
                "\n## 练习任务\n",
            ])
            for i, task in enumerate(practice_tasks[:3], 1):
                desc = str(task.get("description") or task.get("task") or task) if isinstance(task, dict) else str(task)
                readme_lines.append(f"{i}. {desc[:100]}")

        readme_lines.extend([
            "\n## 运行方式\n",
            "```bash",
            "# 根据具体示例文件类型运行",
            "# Python 示例：python example.py",
            "# JavaScript 示例：node example.js",
            "```\n",
            "\n## 注意事项\n",
            "- 本代码仅用于学习参考",
            "- 实际项目中请结合最佳实践进行改进",
            "- 如有问题，请对照课程内容进行调试\n",
        ])

        if summary:
            readme_lines.extend([
                "\n## 总结\n",
                f"{summary[:500]}\n",
            ])

        return "\n".join(readme_lines)

    @classmethod
    def _generate_example_files(cls, unit_content: dict[str, Any]) -> list[tuple[str, str]]:
        """Generate example code files based on unit content."""
        intro = unit_content.get("introduction", "").strip("# \n")
        title = intro.split("\n")[0] if intro else "示例"
        sections = unit_content.get("sections", [])

        files = []

        # Detect language from title or content
        language = cls._detect_language(title, sections)

        # Generate main example file
        if language == "python":
            files.append(("main.py", cls._generate_python_example(title, sections)))
        elif language == "javascript":
            files.append(("main.js", cls._generate_javascript_example(title, sections)))
        else:
            # Default to Python
            files.append(("main.py", cls._generate_python_example(title, sections)))

        # Add a test file
        if language == "python":
            files.append(("test_example.py", cls._generate_python_test()))
        elif language == "javascript":
            files.append(("test_example.js", cls._generate_javascript_test()))

        return files

    @classmethod
    def _detect_language(cls, title: str, sections: list[dict[str, Any]]) -> str:
        """Detect programming language from title and content."""
        text = title.lower()
        for sec in sections:
            text += " " + sec.get("title", "").lower() + " " + sec.get("content", "").lower()

        if any(
            kw in text
            for kw in [
                "python",
                "类",
                "函数",
                "def ",
                "import ",
                "from ",
                "字典",
                "列表",
                "元组",
            ]
        ):
            return "python"
        elif any(
            kw in text
            for kw in ["javascript", "js", "node", "对象", "数组", "函数", "async", "await", "promise"]
        ):
            return "javascript"

        return "python"  # Default to Python

    @classmethod
    def _generate_python_example(cls, title: str, sections: list[dict[str, Any]]) -> str:
        """Generate Python example code."""
        lines = [
            "# -*- coding: utf-8 -*-",
            '"""',
            f"{title} - 示例代码",
            "",
            "本示例展示了核心概念和用法。",
            '"""',
            "",
            "def main():",
            '    """主函数入口。"""',
            f'    print("Starting {title}...")',
            "",
        ]

        # Add section examples
        for i, sec in enumerate(sections[:3], 1):
            sec_title = sec.get("title", f"步骤{i}")
            sec_content = sec.get("content", "")

            # Extract first meaningful line
            code_snippet = ""
            for line in sec_content.split("\n"):
                clean = line.strip("# *-[]_").strip()
                if clean and len(clean) > 10:
                    code_snippet = clean[:80]
                    break

            lines.extend([
                "",
                f"    # {sec_title}",
                f'    print("{sec_title}: {code_snippet}")',
            ])

        lines.extend([
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ])

        return "\n".join(lines)

    @classmethod
    def _generate_javascript_example(cls, title: str, sections: list[dict[str, Any]]) -> str:
        """Generate JavaScript example code."""
        lines = [
            "/**",
            f" * {title} - 示例代码",
            " *",
            " * 本示例展示了核心概念和用法。",
            " */",
            "",
            "function main() {",
            f'    console.log("Starting {title}...");',
            "",
        ]

        # Add section examples
        for i, sec in enumerate(sections[:3], 1):
            sec_title = sec.get("title", f"步骤{i}")
            sec_content = sec.get("content", "")

            # Extract first meaningful line
            code_snippet = ""
            for line in sec_content.split("\n"):
                clean = line.strip("# *-[]_").strip()
                if clean and len(clean) > 10:
                    code_snippet = clean[:80]
                    break

            lines.extend([
                f"    // {sec_title}",
                f'    console.log("{sec_title}: {code_snippet}");',
            ])

        lines.extend([
            "",
            "}",
            "",
            "main();",
            "",
        ])

        return "\n".join(lines)

    @classmethod
    def _generate_python_test(cls) -> str:
        """Generate Python test file."""
        return """# -*- coding: utf-8 -*-
\"\"\"单元测试示例\"\"\"

import unittest


class TestExample(unittest.TestCase):
    def test_example(self):
        self.assertTrue(True)
        print("Test passed!")


if __name__ == "__main__":
    unittest.main()
"""

    @classmethod
    def _generate_javascript_test(cls) -> str:
        """Generate JavaScript test file."""
        return """/**
 * 单元测试示例
 */

function testExample() {
    console.assert(true, "Test passed!");
}

testExample();
"""
