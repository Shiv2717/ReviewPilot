"""Tests for diff filtering, hunk parsing, and chunking."""

from __future__ import annotations

from pathlib import Path

from app.core.schemas import DiffFile
from app.services.diff_processor import (
    annotate_files,
    chunk_files,
    parse_hunks,
    process_pull_files,
    should_ignore_file,
)

FIXTURES = Path(__file__).parent / "fixtures" / "diffs"


def test_ignores_lockfiles_and_minified() -> None:
    assert should_ignore_file("package-lock.json")[0] is True
    assert should_ignore_file("app.min.js")[0] is True
    assert should_ignore_file("logo.png")[0] is True
    assert should_ignore_file("app/main.py")[0] is False


def test_parse_rename_style_hunk_line_numbers() -> None:
    patch = (FIXTURES / "rename.patch").read_text()
    hunks = parse_hunks(patch)
    assert len(hunks) == 1
    assert hunks[0].old_start == 1
    assert hunks[0].new_start == 1
    # Added line should map to new line 2
    assert 2 in [n for n in hunks[0].new_line_numbers if n is not None]


def test_parse_deleted_file() -> None:
    patch = (FIXTURES / "deleted.patch").read_text()
    hunks = parse_hunks(patch)
    assert hunks[0].new_count == 0
    assert all(n is None for n in hunks[0].new_line_numbers)


def test_parse_no_newline_at_eof() -> None:
    patch = (FIXTURES / "no_newline.patch").read_text()
    hunks = parse_hunks(patch)
    assert any(line.startswith("\\") for line in hunks[0].lines)


def test_large_hunk_chunks_under_budget() -> None:
    patch = (FIXTURES / "large_hunk.patch").read_text()
    files = [
        DiffFile(filename="big.py", status="modified", patch=patch),
        DiffFile(filename="yarn.lock", status="modified", patch="@@ -1 +1 @@\n-a\n+b\n"),
    ]
    annotated = annotate_files(files)
    assert annotated[1].ignored is True
    chunks = chunk_files(annotated, token_budget=50)
    assert len(chunks) >= 1
    assert all(c.file_path == "big.py" for c in chunks)


def test_process_pull_files_pipeline() -> None:
    patch = (FIXTURES / "rename.patch").read_text()
    chunks = process_pull_files(
        [DiffFile(filename="greet.py", status="modified", patch=patch)],
        token_budget=1000,
    )
    assert len(chunks) == 1
    assert "FILE: greet.py" in chunks[0].content
