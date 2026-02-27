# CodebaseIndexerV4.py

#!/usr/bin/env python3
from __future__ import annotations

"""
Codebase Indexer v4
A high-performance, multi-threaded indexer for files, symbols, and dependencies.

Changes from v3:
- Parallelized indexing using ProcessPoolExecutor for CPU-bound AST parsing.
- Added SHA-256 content hashing for change detection.
- Expanded symbol extraction for Rust, Go, and TypeScript.
- Optimized I/O using os.scandir for faster directory walking.
- Unified symbol mapping for faster global search.
"""

import ast
import json
import os
import re
import sys
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor

# --- CONFIGURATION ---
if len(sys.argv) > 1:
    ROOT_DIR = Path(sys.argv[1]).resolve()
else:
    ROOT_DIR = Path.cwd()

OUTPUT_DIR = ROOT_DIR / ".indexer_cache"
OUTPUT_FILE = OUTPUT_DIR / "codebase_index_v4.json"

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".next",
    ".turbo",
    ".parcel-cache",
    ".idea",
    ".vscode",
    "vendor",
}

MAX_FILE_SIZE_BYTES = 2_000_000  # 2MB limit

LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
}

# --- DATA MODELS ---


@dataclass
class Symbol:
    name: str
    kind: str
    line: int


@dataclass
class FileMetadata:
    path: str
    file_name: str
    extension: str
    language: str
    size_bytes: int
    line_count: int
    hash: str
    modified_at: str
    tags: List[str]
    dependencies: List[str]
    symbols: List[Symbol]


# --- EXTRACTORS ---


def get_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def extract_python_data(content: str) -> tuple[List[Symbol], List[str]]:
    symbols: List[Symbol] = []
    deps: List[str] = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            # Symbols
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(Symbol(node.name, "function", node.lineno))
            elif isinstance(node, ast.ClassDef):
                symbols.append(Symbol(node.name, "class", node.lineno))
            # Dependencies
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    deps.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps.append(node.module.split(".")[0])
    except SyntaxError:
        pass
    return symbols, sorted(list(set(deps)))


def extract_regex_symbols(content: str, lang: str) -> List[Symbol]:
    """Fallback regex extractor for multiple languages."""
    symbols = []
    patterns = {
        "typescript": [
            (r"(?:export\s+)?(?:class|interface|type)\s+(\w+)", "type"),
            (r"(?:export\s+)?(?:function|const|let)\s+(\w+)\s*=\s*\(", "function"),
            (r"function\s+(\w+)\s*\(", "function"),
        ],
        "rust": [
            (r"fn\s+(\w+)", "function"),
            (r"struct\s+(\w+)", "struct"),
            (r"trait\s+(\w+)", "trait"),
            (r"impl(?:\s+[\w<>, ]+\s+for)?\s+(\w+)", "implementation"),
        ],
        "go": [
            (r"func\s+(\w+)\s*\(", "function"),
            (r"type\s+(\w+)\s+struct", "struct"),
            (r"type\s+(\w+)\s+interface", "interface"),
        ],
    }

    lang_patterns = patterns.get(lang, [(r"^\s*(?:def|func|class)\s+(\w+)", "generic")])

    lines = content.splitlines()
    for idx, line in enumerate(lines, start=1):
        for pattern, kind in lang_patterns:
            match = re.search(pattern, line)
            if match:
                symbols.append(Symbol(match.group(1), kind, idx))
                break
    return symbols


# --- CORE LOGIC ---


def process_single_file(file_path_str: str) -> Optional[Dict[str, Any]]:
    """Worker function for parallel processing."""
    file_path = Path(file_path_str)
    try:
        stat = file_path.stat()
        if stat.st_size > MAX_FILE_SIZE_BYTES:
            return None

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if not content:
            return None

        rel_path = file_path.relative_to(ROOT_DIR)
        ext = file_path.suffix.lower()
        lang = LANGUAGE_MAP.get(ext, "text")

        symbols, deps = [], []
        if lang == "python":
            symbols, deps = extract_python_data(content)
        elif lang in ["typescript", "javascript", "go", "rust"]:
            symbols = extract_regex_symbols(content, lang)
            # Simple JS dependency extraction
            if lang in ["typescript", "javascript"]:
                deps = re.findall(r"from\s+['\"]([^'\s.]+)['\"]", content)

        tags = [f"lang:{lang}", f"size:{'large' if stat.st_size > 100000 else 'small'}"]
        if "test" in str(rel_path).lower():
            tags.append("test")

        meta = FileMetadata(
            path=str(rel_path),
            file_name=file_path.name,
            extension=ext,
            language=lang,
            size_bytes=stat.st_size,
            line_count=len(content.splitlines()),
            hash=get_hash(content),
            modified_at=datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            tags=tags,
            dependencies=sorted(list(set(deps))),
            symbols=symbols,
        )
        return asdict(meta)
    except Exception:
        return None


def iter_files_fast(root: Path) -> Iterable[str]:
    """Walk directory using os.scandir for better performance."""
    try:
        for entry in os.scandir(root):
            if entry.is_dir():
                if entry.name not in IGNORE_DIRS and not entry.name.startswith("."):
                    yield from iter_files_fast(Path(entry.path))
            elif entry.is_file():
                if Path(entry.name).suffix.lower() in LANGUAGE_MAP:
                    yield entry.path
    except PermissionError:
        pass


def main():
    print(f"Indexing Codebase: {ROOT_DIR}")
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 1. Collect all files
    file_list = list(iter_files_fast(ROOT_DIR))
    print(f"Found {len(file_list)} candidate files...")

    # 2. Process in parallel
    results = []
    with ProcessPoolExecutor() as executor:
        # Use map to distribute file processing across CPU cores
        for res in executor.map(process_single_file, file_list):
            if res:
                results.append(res)

    # 3. Build Global Symbol Map and Stats
    symbol_map = defaultdict(list)
    lang_stats = Counter()
    total_lines = 0

    for f in results:
        lang_stats[f["language"]] += 1
        total_lines += f["line_count"]
        for sym in f["symbols"]:
            symbol_map[sym["name"]].append(
                {"file": f["path"], "kind": sym["kind"], "line": sym["line"]}
            )

    # 4. Final Export
    index_data = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "root_dir": str(ROOT_DIR),
            "file_count": len(results),
            "total_lines": total_lines,
            "languages": dict(lang_stats),
        },
        "files": results,
        "symbol_index": dict(symbol_map),
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)

    print(f"Success! Indexed {len(results)} files.")
    print(f"Database: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
