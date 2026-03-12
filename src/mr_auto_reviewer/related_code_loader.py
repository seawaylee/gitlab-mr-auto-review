import re
from collections import deque
from pathlib import PurePosixPath
from typing import Callable, Iterable, List, Optional

from .models import Change, CodeContext


class RelatedCodeLoader:
    def __init__(
        self,
        file_loader: Callable[[str, str], Optional[str]],
        path_resolver: Optional[Callable[[str, str], List[str]]] = None,
        max_context_files: int = 8,
        max_depth: int = 2,
        max_file_chars: int = 4000,
    ):
        self.file_loader = file_loader
        self.path_resolver = path_resolver
        self.max_context_files = max_context_files
        self.max_depth = max_depth
        self.max_file_chars = max_file_chars

    def load(self, changes: list[Change], ref: str) -> list[CodeContext]:
        queue = deque()
        for change in changes:
            path = (change.new_path or "").strip()
            if path:
                queue.append((path, 0, "changed_file"))

        seen: set[str] = set()
        contexts: list[CodeContext] = []
        while queue and len(contexts) < self.max_context_files:
            path, depth, reason = queue.popleft()
            if path in seen:
                continue
            seen.add(path)

            content = self.file_loader(path, ref)
            if not content:
                if self.path_resolver:
                    for resolved_path in self.path_resolver(path, ref):
                        if resolved_path not in seen:
                            queue.appendleft((resolved_path, depth, reason))
                continue
            snippet = content.strip()[: self.max_file_chars].strip()
            if not snippet:
                continue

            contexts.append(
                CodeContext(
                    path=path,
                    depth=depth,
                    reason=reason,
                    content=snippet,
                )
            )
            if depth >= self.max_depth:
                continue

            next_reason = "imported_by_changed_file" if depth == 0 else "imported_by_related_file"
            for candidate in self._extract_related_paths(path=path, content=snippet):
                if candidate not in seen:
                    queue.append((candidate, depth + 1, next_reason))
        return contexts

    def _extract_related_paths(self, path: str, content: str) -> Iterable[str]:
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".java", ".kt"}:
            return self._extract_java_like_import_paths(path=path, content=content)
        if suffix == ".py":
            return self._extract_python_import_paths(path=path, content=content)
        if suffix in {".js", ".jsx", ".ts", ".tsx"}:
            return self._extract_js_like_import_paths(path=path, content=content)
        return []

    def _extract_java_like_import_paths(self, path: str, content: str) -> list[str]:
        base_prefix = ""
        marker = ""
        if "/src/main/java/" in path:
            marker = "/src/main/java/"
        elif "/src/test/java/" in path:
            marker = "/src/test/java/"
        if marker:
            base_prefix = path.split(marker, 1)[0] + marker

        results: list[str] = []
        pattern = re.compile(r"^\s*import\s+([a-zA-Z_][\w.]+)\s*;", re.MULTILINE)
        for match in pattern.findall(content):
            if match.startswith(("java.", "javax.", "jakarta.", "org.", "com.fasterxml.", "lombok.")):
                continue
            results.append(f"{base_prefix}{match.replace('.', '/')}.java")
        return results

    def _extract_python_import_paths(self, path: str, content: str) -> list[str]:
        current_dir = PurePosixPath(path).parent
        results: list[str] = []

        import_pattern = re.compile(r"^\s*import\s+([a-zA-Z_][\w., ]*)", re.MULTILINE)
        for group in import_pattern.findall(content):
            for module_name in [part.strip() for part in group.split(",") if part.strip()]:
                module_path = module_name.replace(".", "/")
                results.extend(
                    [
                        str(current_dir / f"{module_path}.py"),
                        f"{module_path}.py",
                    ]
                )

        from_pattern = re.compile(r"^\s*from\s+([a-zA-Z_][\w.]*)\s+import\s+", re.MULTILINE)
        for module_name in from_pattern.findall(content):
            module_path = module_name.replace(".", "/")
            results.extend(
                [
                    str(current_dir / f"{module_path}.py"),
                    f"{module_path}.py",
                ]
            )
        return results

    def _extract_js_like_import_paths(self, path: str, content: str) -> list[str]:
        current_dir = PurePosixPath(path).parent
        results: list[str] = []
        pattern = re.compile(r"""(?:import|require)\s*(?:.+?\s+from\s+)?["']([^"']+)["']""")
        for raw_module in pattern.findall(content):
            if not raw_module.startswith("."):
                continue
            resolved = (current_dir / raw_module).as_posix()
            if PurePosixPath(resolved).suffix:
                results.append(resolved)
                continue
            for extension in (".ts", ".tsx", ".js", ".jsx"):
                results.append(f"{resolved}{extension}")
        return results
