#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Dict, Any, Tuple
import sqlite3

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

CONFIG = {
    "MAX_FILE_SIZE_BYTES": 2_000_000,
    "EMBEDDING_MODEL": "all-MiniLM-L6-v2" if SENTENCE_TRANSFORMERS_AVAILABLE else None,
    "DB_PATH": ".indexer_cache/codebase.db",
}

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

ROOT_DIR = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()


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
    content_summary: str


def get_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()


def extract_python_data(content: str) -> Tuple[List[Symbol], List[str]]:
    symbols: List[Symbol] = []
    deps: List[str] = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(Symbol(node.name, "function", node.lineno))
            elif isinstance(node, ast.ClassDef):
                symbols.append(Symbol(node.name, "class", node.lineno))
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


def generate_content_summary(file_path: Path, lang: str, symbols: List[Symbol]) -> str:
    parts = [f"File: {file_path.name}"]
    if symbols:
        symbol_types = Counter(s.kind for s in symbols)
        parts.append(
            f"Contains {len(symbols)} symbols: {', '.join(f'{k}: {v}' for k, v in symbol_types.items())}"
        )
    if lang != "text":
        parts.append(f"Language: {lang}")
    return ". ".join(parts)


def process_single_file(file_path_str: str) -> Optional[Dict[str, Any]]:
    file_path = Path(file_path_str)
    try:
        stat = file_path.stat()
        if stat.st_size > CONFIG["MAX_FILE_SIZE_BYTES"]:
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
            if lang in ["typescript", "javascript"]:
                deps = re.findall(r"from\s+['\"]([^'\s.]+)['\"]", content)

        tags = [f"lang:{lang}", f"size:{'large' if stat.st_size > 100000 else 'small'}"]
        if "test" in str(rel_path).lower():
            tags.append("test")
        if "route" in str(rel_path).lower():
            tags.append("route")
        if "component" in str(rel_path).lower():
            tags.append("component")
        if (
            "durable-object" in str(rel_path).lower()
            or "durable" in str(rel_path).lower()
        ):
            tags.append("durable-object")

        content_summary = generate_content_summary(rel_path, lang, symbols)

        meta = {
            "path": str(rel_path),
            "file_name": file_path.name,
            "extension": ext,
            "language": lang,
            "size_bytes": stat.st_size,
            "line_count": len(content.splitlines()),
            "hash": get_hash(content),
            "modified_at": datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            ).isoformat(),
            "tags": tags,
            "dependencies": sorted(list(set(deps))),
            "symbols": [
                {"name": s.name, "kind": s.kind, "line": s.line} for s in symbols
            ],
            "content_summary": content_summary,
        }
        return meta
    except Exception:
        return None


def iter_files_fast(root: Path) -> Iterable[str]:
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


def init_database(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE,
            file_name TEXT,
            extension TEXT,
            language TEXT,
            size_bytes INTEGER,
            line_count INTEGER,
            hash TEXT,
            modified_at TEXT,
            content_summary TEXT,
            tags_json TEXT,
            dependencies_json TEXT,
            symbols_json TEXT,
            embedding BLOB
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            kind TEXT,
            file_id INTEGER,
            line INTEGER,
            FOREIGN KEY (file_id) REFERENCES files (id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_language ON files(language)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_tags ON files(tags_json)")

    conn.commit()
    return conn


def main():
    db_path = ROOT_DIR / CONFIG["DB_PATH"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Indexing Codebase: {ROOT_DIR}")
    print(f"Database: {db_path}")

    conn = init_database(str(db_path))
    cursor = conn.cursor()

    cursor.execute("DELETE FROM files")
    cursor.execute("DELETE FROM symbols")
    cursor.execute("DELETE FROM metadata")

    file_list = list(iter_files_fast(ROOT_DIR))
    print(f"Found {len(file_list)} candidate files...")

    results = []
    for file_path in file_list:
        res = process_single_file(file_path)
        if res:
            results.append(res)

    print(f"Processed {len(results)} files...")

    model = None
    try:
        if CONFIG["EMBEDDING_MODEL"]:
            model = SentenceTransformer(CONFIG["EMBEDDING_MODEL"])
    except Exception as e:
        print(f"Warning: Could not load embedding model: {e}")

    for file_data in results:
        cursor.execute(
            """
            INSERT INTO files (
                path, file_name, extension, language, size_bytes, line_count,
                hash, modified_at, content_summary, tags_json, dependencies_json, symbols_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                file_data["path"],
                file_data["file_name"],
                file_data["extension"],
                file_data["language"],
                file_data["size_bytes"],
                file_data["line_count"],
                file_data["hash"],
                file_data["modified_at"],
                file_data["content_summary"],
                json.dumps(file_data["tags"]),
                json.dumps(file_data["dependencies"]),
                json.dumps(file_data["symbols"]),
            ),
        )

        file_id = cursor.lastrowid

        for sym in file_data["symbols"]:
            cursor.execute(
                """
                INSERT INTO symbols (name, kind, file_id, line)
                VALUES (?, ?, ?, ?)
            """,
                (sym["name"], sym["kind"], file_id, sym["line"]),
            )

    if model:
        print("Generating embeddings...")
        cursor.execute("SELECT id, content_summary FROM files")
        file_ids_summaries = cursor.fetchall()

        for file_id, summary in file_ids_summaries:
            embedding = model.encode(summary, convert_to_numpy=True)
            cursor.execute(
                "UPDATE files SET embedding = ? WHERE id = ?",
                (embedding.tobytes(), file_id),
            )

    lang_stats = Counter()
    total_lines = 0
    for f in results:
        lang_stats[f["language"]] += 1
        total_lines += f["line_count"]

    cursor.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
    """,
        ("generated_at", datetime.now(timezone.utc).isoformat()),
    )
    cursor.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
    """,
        ("root_dir", str(ROOT_DIR)),
    )
    cursor.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
    """,
        ("file_count", str(len(results))),
    )
    cursor.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
    """,
        ("total_lines", str(total_lines)),
    )
    cursor.execute(
        """
        INSERT INTO metadata (key, value) VALUES (?, ?)
    """,
        ("languages", json.dumps(dict(lang_stats))),
    )

    conn.commit()
    conn.close()

    print(f"Success! Indexed {len(results)} files.")
    print(f"Total lines: {total_lines}")
    print(f"Languages: {', '.join(f'{k}: {v}' for k, v in lang_stats.items())}")
    if model:
        print(f"Embeddings generated using {CONFIG['EMBEDDING_MODEL']}")
    else:
        print(
            "Note: sentence-transformers not installed. Run: uv pip install sentence-transformers"
        )


if __name__ == "__main__":
    main()
