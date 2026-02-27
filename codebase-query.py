#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

DB_PATH = ".indexer_cache/codebase.db"
ROOT_DIR = Path.cwd()


class CodebaseQuery:
    def __init__(self, db_path: str = None, model: str = "all-MiniLM-L6-v2"):
        self.db_path = Path(db_path) if db_path else Path(ROOT_DIR) / DB_PATH
        self.model_name = model
        self.conn = sqlite3.connect(str(self.db_path))
        self.model = (
            SentenceTransformer(model) if SENTENCE_TRANSFORMERS_AVAILABLE else None
        )
        self.embedding_dim = 384 if self.model else None

    def close(self):
        self.conn.close()

    def get_metadata(self) -> Dict[str, Any]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT key, value FROM metadata")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def find_files_by_language(self, language: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE language = ?", (language,))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def find_files_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM files WHERE tags_json LIKE ?", (f"%{tag}%",))
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def find_symbol(self, symbol_name: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT s.*, f.path, f.file_name, f.language
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.name LIKE ?
        """,
            (f"%{symbol_name}%",),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def find_symbols_by_kind(self, kind: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT s.*, f.path, f.file_name, f.language
            FROM symbols s
            JOIN files f ON s.file_id = f.id
            WHERE s.kind = ?
            ORDER BY f.path, s.line
        """,
            (kind,),
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_files_by_dependency(self, dependency: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM files WHERE dependencies_json LIKE ?", (f"%{dependency}%",)
        )
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def semantic_search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.model:
            print(
                "Note: sentence-transformers not available. Install with: uv pip install sentence-transformers"
            )
            return []

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, path, content_summary, embedding FROM files WHERE embedding IS NOT NULL"
        )
        rows = cursor.fetchall()

        if not rows:
            return []

        query_embedding = self.model.encode(query, convert_to_numpy=True)

        results = []
        for row in rows:
            file_id, path, summary, embedding_blob = row
            file_embedding = np.frombuffer(embedding_blob, dtype=np.float32)
            similarity = np.dot(query_embedding, file_embedding)
            results.append(
                {
                    "file_id": file_id,
                    "path": path,
                    "summary": summary,
                    "similarity": float(similarity),
                }
            )

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def get_entry_points(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()

        entry_points = []

        cursor.execute("""
            SELECT f.* 
            FROM files f
            WHERE (f.file_name LIKE '%index%' OR f.file_name LIKE '%main%' OR f.file_name LIKE '%app%')
            AND (f.extension = '.tsx' OR f.extension = '.ts' OR f.extension = '.jsx' OR f.extension = '.js')
            ORDER BY f.path
        """)
        columns = [desc[0] for desc in cursor.description]
        entry_points.extend([dict(zip(columns, row)) for row in cursor.fetchall()])

        cursor.execute("SELECT * FROM files WHERE path LIKE '%client.tsx%'")
        entry_points.extend([dict(zip(columns, row)) for row in cursor.fetchall()])

        cursor.execute("SELECT * FROM files WHERE path LIKE '%ssr.tsx%'")
        entry_points.extend([dict(zip(columns, row)) for row in cursor.fetchall()])

        return entry_points

    def get_routes(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT f.* 
            FROM files f
            WHERE (f.path LIKE '%routes%' OR f.path LIKE '%router%')
            ORDER BY f.path
        """)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_components(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT f.* 
            FROM files f
            WHERE (f.path LIKE '%components%' OR f.file_name LIKE '%Component%' OR f.tags_json LIKE '%component%')
            ORDER BY f.path
        """)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_durable_objects(self) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT f.* 
            FROM files f
            WHERE f.path LIKE '%durable-object%' OR f.tags_json LIKE '%durable-object%'
            ORDER BY f.path
        """)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def print_results(self, results: List[Dict[str, Any]], show_details: bool = False):
        if not results:
            print("No results found.")
            return

        print(f"\nFound {len(results)} result(s):\n")
        for i, r in enumerate(results, 1):
            print(f"{i}. {r.get('path', r.get('name', '?'))}")
            if "line" in r:
                print(f"   Line {r['line']} ({r['kind']})")
            if "file_name" in r and "language" in r:
                print(f"   File: {r['file_name']} ({r['language']})")
            if "summary" in r:
                print(f"   {r['summary']}")
            if "similarity" in r:
                print(f"   Similarity: {r['similarity']:.3f}")
            if show_details:
                print(f"   Details: {json.dumps(r, indent=2, default=str)}")
            print()


def main():
    if len(sys.argv) < 2:
        print("Codebase Query CLI")
        print("\nUsage:")
        print("  python codebase-query.py <command> [options]")
        print("\nCommands:")
        print("  info                    Show metadata about the indexed codebase")
        print(
            "  lang <language>         Find files by language (e.g., typescript, python)"
        )
        print("  tag <tag>               Find files by tag (e.g., component, route)")
        print("  symbol <name>           Find symbols by name")
        print(
            "  symbols <kind>          Find symbols by kind (e.g., function, class, type)"
        )
        print("  dep <dependency>        Find files using a dependency")
        print("  search <query>          Semantic search (requires embeddings)")
        print("  entry-points            Show application entry points")
        print("  routes                  Show all route files")
        print("  components              Show all component files")
        print("  durable-objects         Show Durable Object files")
        print("\nExamples:")
        print("  python codebase-query.py info")
        print("  python codebase-query.py lang typescript")
        print("  python codebase-query.py symbol ChatSession")
        print("  python codebase-query.py search 'where is chat stored'")
        print("  python codebase-query.py entry-points")
        sys.exit(1)

    db_path = None
    if len(sys.argv) > 2 and sys.argv[1] == "--db":
        db_path = sys.argv[2]
        sys.argv.pop(0)
        sys.argv.pop(0)

    command = sys.argv[1].lower()
    args = sys.argv[2:]

    try:
        query = CodebaseQuery(db_path)

        if command == "info":
            metadata = query.get_metadata()
            print("Codebase Index Information:")
            for key, value in metadata.items():
                if key == "languages":
                    langs = json.loads(value)
                    print(
                        f"  {key}: {', '.join(f'{k}: {v}' for k, v in langs.items())}"
                    )
                else:
                    print(f"  {key}: {value}")

        elif command == "lang":
            if not args:
                print("Error: Language required")
                sys.exit(1)
            results = query.find_files_by_language(args[0])
            query.print_results(results)

        elif command == "tag":
            if not args:
                print("Error: Tag required")
                sys.exit(1)
            results = query.find_files_by_tag(args[0])
            query.print_results(results)

        elif command == "symbol":
            if not args:
                print("Error: Symbol name required")
                sys.exit(1)
            results = query.find_symbol(args[0])
            query.print_results(results)

        elif command == "symbols":
            if not args:
                print("Error: Symbol kind required")
                sys.exit(1)
            results = query.find_symbols_by_kind(args[0])
            query.print_results(results)

        elif command == "dep":
            if not args:
                print("Error: Dependency required")
                sys.exit(1)
            results = query.get_files_by_dependency(args[0])
            query.print_results(results)

        elif command == "search":
            if not args:
                print("Error: Search query required")
                sys.exit(1)
            query_text = " ".join(args)
            results = query.semantic_search(query_text, limit=10)
            query.print_results(results)

        elif command == "entry-points":
            results = query.get_entry_points()
            query.print_results(results)

        elif command == "routes":
            results = query.get_routes()
            query.print_results(results)

        elif command == "components":
            results = query.get_components()
            query.print_results(results)

        elif command == "durable-objects":
            results = query.get_durable_objects()
            query.print_results(results)

        else:
            print(f"Unknown command: {command}")
            print("Run without arguments to see usage.")
            sys.exit(1)

        query.close()

    except sqlite3.OperationalError as e:
        print(f"Error: Database not found or corrupted. Run the indexer first.")
        print(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
