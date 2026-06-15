import fnmatch
import logging
import math
import os
import re
import shutil
import tempfile
from collections import OrderedDict
from pathlib import Path
from .local import LocalProcessor
from .git import GitProcessor
from .web import WebProcessor
from .config import (
    BINARY_REF_SUFFIX,
    COLLECTABLE_BINARIES,
    DEFAULT_IGNORE_PATTERNS,
    ENTRY_NAMES,
    MANIFEST_NAMES,
)

logger = logging.getLogger(__name__)

PACKING_OVERHEAD_RATIO = 1.15
PACKING_OVERHEAD_PER_FILE_BYTES = 4096
MIN_RETRY_SPLIT_GROWTH_MB = 1

class RepositoryProcessor:
    def __init__(self, log_callback=None, progress_callback=None):
        self.local_processor = LocalProcessor(log_callback, progress_callback)
        self.git_processor = GitProcessor(log_callback, progress_callback)
        self.web_processor = WebProcessor(log_callback, progress_callback)
        self.log_callback = log_callback

    def log(self, message):
        if self.log_callback:
            self.log_callback(message)

    def process_repo(self, root_dir, output_file, extra_ignores=None, include_patterns=None, 
                     style="markdown", split_size=None, header_text=None, collect_binaries=True,
                     max_tokens=None):
        planning = self.plan_local_processing(
            root_dir,
            include_patterns=include_patterns,
            extra_ignores=extra_ignores,
            requested_split_size=split_size,
            max_tokens=max_tokens,
        )
        effective_split_size = planning["effective_split_size"]

        token_limited_split_size = planning["token_limited_split_size"]
        if (
            split_size
            and token_limited_split_size is not None
            and token_limited_split_size < split_size
        ):
            self.log(
                f"Applying token-based split target: {token_limited_split_size}MB "
                f"(from max_tokens={max_tokens})."
            )

        if planning["largest_file_adjusted"]:
            self.log(
                "Warning: Detected a large local file "
                f"({planning['largest_file_size_mb']}MB at {planning['largest_file_path']}). "
                f"Increasing split limit to {effective_split_size}MB to prevent Repomix crashes."
            )
        
        run_folder = os.path.dirname(output_file)
        binary_stats = {"count": 0, "files": []}
        
        # 1. Orchestrate Binaries (Copying)
        if collect_binaries:
            self.log("Orchestrating binary files (copying)...")
            binary_stats = self._orchestrate_binaries(root_dir, run_folder, extra_ignores)
            if binary_stats["count"] > 0:
                self.log(f"Copied {binary_stats['count']} binary files to output folder.")

        # 2. Process with Repomix
        if planning["batch_count"] > 1:
            self.log(
                f"Batching local repository into {planning['batch_count']} curated packs "
                f"(target {effective_split_size}MB per batch)."
            )
            stats = self._process_local_batches(
                root_dir,
                output_file,
                planning,
                style=style,
                header_text=header_text,
            )
        else:
            stats, effective_split_size = self._run_local_process_with_retry(
                root_dir=root_dir,
                output_file=output_file,
                extra_ignores=extra_ignores,
                include_patterns=include_patterns,
                style=style,
                split_size=effective_split_size,
                header_text=header_text,
            )
        
        # 3. Inject binary stats into result
        if stats:
            used_split_size = stats.get("used_split_size", effective_split_size)
            stats["binary_attachments"] = binary_stats["count"]
            stats["planned_split_size"] = used_split_size
            stats["largest_included_file_mb"] = planning["largest_file_size_mb"]
            stats["largest_included_file_path"] = planning["largest_file_path"]
            stats["batch_count"] = planning["batch_count"]
            stats["estimated_included_size_mb"] = planning["estimated_total_size_mb"]
        
        return stats

    def plan_local_processing(self, root_dir, include_patterns=None, extra_ignores=None,
                              requested_split_size=None, max_tokens=None):
        included_files = list(
            self._iter_included_files(root_dir, include_patterns, extra_ignores)
        )
        addon_roots = self._find_odoo_addon_roots(root_dir, included_files)

        files = []
        largest_file_size_mb = 0
        largest_file_path = None
        estimated_total_size_bytes = 0

        for file_path in included_files:
            stat_result = file_path.stat()
            size_bytes = stat_result.st_size
            size_mb = max(1, math.ceil(size_bytes / (1024 * 1024)))
            rel_path = file_path.relative_to(root_dir).as_posix()
            files.append({
                "path": file_path,
                "rel_path": rel_path,
                "size_bytes": size_bytes,
                "size_mb": size_mb,
                "estimated_packed_bytes": self._estimate_packed_size_bytes(rel_path, size_bytes),
                "priority": self._get_file_priority(rel_path),
                "group_key": self._get_group_key(rel_path, addon_roots),
            })
            estimated_total_size_bytes += size_bytes
            if size_mb > largest_file_size_mb:
                largest_file_size_mb = size_mb
                largest_file_path = rel_path

        token_limited_split_size = self._apply_token_split_limit(requested_split_size, max_tokens)
        effective_split_size = token_limited_split_size
        largest_file_adjusted = False

        if effective_split_size is not None and largest_file_size_mb >= effective_split_size:
            effective_split_size = largest_file_size_mb + 1
            largest_file_adjusted = True

        batches = self._build_batches(files, effective_split_size)

        return {
            "requested_split_size": requested_split_size,
            "token_limited_split_size": token_limited_split_size,
            "effective_split_size": effective_split_size,
            "largest_file_size_mb": largest_file_size_mb,
            "largest_file_path": largest_file_path,
            "largest_file_adjusted": largest_file_adjusted,
            "estimated_total_size_mb": max(1, math.ceil(estimated_total_size_bytes / (1024 * 1024))) if files else 0,
            "total_included_files": len(files),
            "files": files,
            "batches": batches,
            "batch_count": len(batches),
        }

    def _find_odoo_addon_roots(self, root_dir, included_files):
        root_path = Path(root_dir)
        addon_roots = []
        for file_path in included_files:
            if file_path.name == "__manifest__.py":
                addon_roots.append(file_path.parent.relative_to(root_path).as_posix())
        return sorted(addon_roots, key=len, reverse=True)

    def _iter_included_files(self, root_dir, include_patterns=None, extra_ignores=None):
        root_path = Path(root_dir)
        ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        if extra_ignores:
            ignore_patterns.extend(extra_ignores)

        normalized_includes = self._normalize_include_patterns(include_patterns)

        for current_root, dirnames, filenames in os.walk(root_path):
            current_root_path = Path(current_root)

            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not self._matches_patterns(
                    (current_root_path / dirname).relative_to(root_path).as_posix() + "/",
                    ignore_patterns,
                )
            ]

            for filename in filenames:
                file_path = current_root_path / filename
                rel_path = file_path.relative_to(root_path).as_posix()

                if self._matches_patterns(rel_path, ignore_patterns):
                    continue

                if normalized_includes and not self._matches_patterns(rel_path, normalized_includes):
                    continue

                yield file_path

    def _apply_token_split_limit(self, split_size, max_tokens):
        if not max_tokens:
            return split_size

        # Heuristic: 1 token/word ~ 6 bytes including overhead.
        # This is more realistic than the previous 10x multiplier.
        estimated_mb = max(1, int(max_tokens * 6 / (1024 * 1024)))
        if split_size is None:
            return estimated_mb

        return min(split_size, estimated_mb)

    def _normalize_include_patterns(self, include_patterns):
        if not include_patterns:
            return []

        normalized = []
        for pattern in include_patterns:
            if "." not in pattern and "*" not in pattern:
                normalized.append(f"**/*.{pattern}")
            else:
                normalized.append(pattern)
        return normalized

    def _matches_patterns(self, rel_path, patterns):
        normalized_path = rel_path.replace(os.sep, "/").lstrip("./")

        for pattern in patterns:
            normalized_pattern = pattern.replace(os.sep, "/")
            if fnmatch.fnmatch(normalized_path, normalized_pattern):
                return True

            if normalized_pattern.startswith("**/") and fnmatch.fnmatch(
                normalized_path, normalized_pattern[3:]
            ):
                return True

            if normalized_pattern.endswith("/**"):
                prefix = normalized_pattern[:-3].rstrip("/")
                if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
                    return True

            if "*" not in normalized_pattern and "?" not in normalized_pattern:
                prefix = normalized_pattern.rstrip("/")
                if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
                    return True

        return False

    def _build_batches(self, files, split_size_mb):
        if not files:
            return []

        ordered_files = sorted(
            files,
            key=lambda item: (item["priority"], item["group_key"], item["rel_path"]),
        )
        if not split_size_mb:
            return [self._make_batch(1, ordered_files)]

        target_bytes = split_size_mb * 1024 * 1024
        batches = []
        current_files = []
        current_bytes = 0

        for group_files in self._group_files_for_batching(ordered_files):
            group_bytes = sum(max(file_info["estimated_packed_bytes"], 1) for file_info in group_files)

            if group_bytes > target_bytes:
                if current_files:
                    batches.append(self._make_batch(len(batches) + 1, current_files))
                    current_files = []
                    current_bytes = 0

                split_group_batches = self._split_group_into_batches(group_files, target_bytes)
                for split_group in split_group_batches:
                    batches.append(self._make_batch(len(batches) + 1, split_group))
                continue

            if current_files and current_bytes + group_bytes > target_bytes:
                batches.append(self._make_batch(len(batches) + 1, current_files))
                current_files = []
                current_bytes = 0

            current_files.extend(group_files)
            current_bytes += group_bytes

        if current_files:
            batches.append(self._make_batch(len(batches) + 1, current_files))

        return batches

    def _group_files_for_batching(self, ordered_files):
        grouped_files = OrderedDict()
        for file_info in ordered_files:
            grouped_files.setdefault(
                (file_info["priority"], file_info["group_key"]),
                [],
            ).append(file_info)
        return grouped_files.values()

    def _split_group_into_batches(self, group_files, target_bytes):
        batches = []
        current_files = []
        current_bytes = 0

        for file_info in group_files:
            file_bytes = max(file_info["estimated_packed_bytes"], 1)
            if current_files and current_bytes + file_bytes > target_bytes:
                batches.append(current_files)
                current_files = []
                current_bytes = 0

            current_files.append(file_info)
            current_bytes += file_bytes

        if current_files:
            batches.append(current_files)

        return batches

    def _make_batch(self, index, files):
        total_size_bytes = sum(file_info["size_bytes"] for file_info in files)
        estimated_packed_bytes = sum(file_info["estimated_packed_bytes"] for file_info in files)
        return {
            "index": index,
            "files": files,
            "file_count": len(files),
            "estimated_size_bytes": total_size_bytes,
            "estimated_size_mb": max(1, math.ceil(total_size_bytes / (1024 * 1024))) if files else 0,
            "estimated_packed_bytes": estimated_packed_bytes,
            "estimated_packed_mb": max(1, math.ceil(estimated_packed_bytes / (1024 * 1024))) if files else 0,
            "first_file": files[0]["rel_path"] if files else None,
        }

    def _estimate_packed_size_bytes(self, rel_path, size_bytes):
        extension = Path(rel_path).suffix.lower()
        ratio = PACKING_OVERHEAD_RATIO
        if extension in {".xml", ".html", ".rst", ".md", ".txt"}:
            ratio += 0.05
        if extension in {".csv", ".json", ".yml", ".yaml"}:
            ratio += 0.03
        return max(size_bytes, int(size_bytes * ratio) + PACKING_OVERHEAD_PER_FILE_BYTES)

    def _get_file_priority(self, rel_path):
        path = Path(rel_path)
        name = path.name.lower()
        path_lower = rel_path.lower()

        if name == "readme.md":
            return 0
        if name in {manifest.lower() for manifest in MANIFEST_NAMES}:
            return 1
        if name in {entry.lower() for entry in ENTRY_NAMES}:
            return 2
        if path_lower.startswith("docs/") or name.endswith((".md", ".rst", ".txt")):
            return 3
        return 4

    def _get_group_key(self, rel_path, addon_roots=None):
        path = Path(rel_path)
        name = path.name.lower()

        addon_root = self._find_containing_addon_root(rel_path, addon_roots or [])
        if addon_root:
            return addon_root

        if name == "readme.md":
            return rel_path
        if name in {manifest.lower() for manifest in MANIFEST_NAMES}:
            return rel_path
        if name in {entry.lower() for entry in ENTRY_NAMES}:
            return path.parent.as_posix() or "."

        parent = path.parent.as_posix()
        return parent if parent and parent != "." else "."

    def _find_containing_addon_root(self, rel_path, addon_roots):
        for addon_root in addon_roots:
            if rel_path == addon_root or rel_path.startswith(addon_root + "/"):
                return addon_root
        return None

    def _process_local_batches(self, root_dir, output_file, planning, style, header_text):
        aggregate = {
            "total_processed": 0,
            "total_tokens": 0,
            "total_chars": 0,
            "total_words": 0,
            "security": "Unknown",
            "top_files": [],
            "batching_applied": True,
            "batch_outputs": [],
        }

        output_path = Path(output_file)
        security_values = []

        for batch in planning["batches"]:
            batch_output = self._get_batch_output_path(output_path, batch["index"])
            batch_header_text = self._build_batch_header_text(
                header_text,
                batch["index"],
                planning["batch_count"],
            )

            with tempfile.TemporaryDirectory(dir=output_path.parent, prefix=f".batch_{batch['index']:03d}_") as stage_dir:
                self._stage_batch_files(root_dir, stage_dir, batch["files"])
                batch_stats, used_split_size = self._run_local_process_with_retry(
                    root_dir=stage_dir,
                    output_file=str(batch_output),
                    extra_ignores=[],
                    include_patterns=[],
                    style=style,
                    split_size=planning["effective_split_size"],
                    header_text=batch_header_text,
                )

            aggregate["batch_outputs"].append(batch_output.name)
            aggregate["total_processed"] += batch_stats.get("total_processed", 0)
            aggregate["total_tokens"] += batch_stats.get("total_tokens", 0)
            aggregate["total_chars"] += batch_stats.get("total_chars", 0)
            aggregate["total_words"] += batch_stats.get("total_words", 0)
            aggregate.setdefault("used_split_sizes", []).append(used_split_size)

            if batch_stats.get("security"):
                security_values.append(batch_stats["security"])

            for file_info in batch_stats.get("top_files", []):
                aggregate["top_files"].append(file_info)

        aggregate["top_files"] = sorted(
            aggregate["top_files"],
            key=lambda item: int(str(item.get("tokens", "0")).replace(",", "")),
            reverse=True,
        )[:5]
        aggregate["security"] = self._summarize_security(security_values)
        aggregate["used_split_size"] = max(aggregate.get("used_split_sizes", [planning["effective_split_size"]]))
        aggregate["index_file"] = self._write_batch_index(output_path.parent, output_path.name, planning, aggregate)
        return aggregate

    def _run_local_process_with_retry(self, root_dir, output_file, extra_ignores,
                                      include_patterns, style, split_size, header_text):
        current_split_size = split_size
        try:
            stats = self.local_processor.process(
                root_dir,
                output_file,
                extra_ignores,
                include_patterns,
                style,
                current_split_size,
                header_text,
            )
            self._sanitize_output_files(output_file)
            return stats, current_split_size
        except RuntimeError as error:
            retry_split_size = self._get_retry_split_size(current_split_size, str(error))
            if retry_split_size is None:
                raise

            self.log(
                f"Repomix split retry: increasing split size from {current_split_size}MB "
                f"to {retry_split_size}MB after root-entry overflow."
            )
            stats = self.local_processor.process(
                root_dir,
                output_file,
                extra_ignores,
                include_patterns,
                style,
                retry_split_size,
                header_text,
            )
            self._sanitize_output_files(output_file)
            return stats, retry_split_size

    def _sanitize_output_files(self, output_file):
        """Discovers and sanitizes all generated files (primary and splits)."""
        output_path = Path(output_file)
        base_name = output_path.stem
        ext = output_path.suffix
        directory = output_path.parent
        
        # Discover related files using same logic as word counter
        for file in directory.iterdir():
            if file.name == output_path.name or (file.stem.startswith(f"{base_name}.") and file.suffix == ext):
                self._wrap_long_lines(file)

    def _wrap_long_lines(self, file_path, max_len=10000):
        """Wraps lines longer than max_len to avoid text processor limits."""
        temp_path = file_path.with_suffix(file_path.suffix + ".wrap_tmp")
        needs_write = False
        
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as src:
                with open(temp_path, "w", encoding="utf-8") as dst:
                    for line in src:
                        if len(line) > max_len:
                            needs_write = True
                            # Chunk long lines
                            for i in range(0, len(line), max_len):
                                chunk = line[i : i + max_len]
                                dst.write(chunk)
                                # Add newline if chunk doesn't end with one
                                if not chunk.endswith("\n"):
                                    dst.write("\n")
                        else:
                            dst.write(line)
            
            if needs_write:
                self.log(f"Wrapped extremely long lines in {file_path.name}")
                temp_path.replace(file_path)
            else:
                temp_path.unlink()
        except Exception as e:
            self.log(f"Warning: Could not sanitize {file_path}: {e}")
            if temp_path.exists():
                temp_path.unlink()

    def _get_retry_split_size(self, split_size, error_message):
        if not split_size:
            return None

        oversize_match = re.search(
            r"Part size ([\d,]+) bytes > limit ([\d,]+) bytes",
            error_message,
        )
        if not oversize_match:
            return None

        part_size = int(oversize_match.group(1).replace(",", ""))
        next_split_mb = math.ceil(part_size / (1024 * 1024)) + MIN_RETRY_SPLIT_GROWTH_MB
        if next_split_mb <= split_size:
            next_split_mb = split_size + MIN_RETRY_SPLIT_GROWTH_MB
        return next_split_mb

    def _get_batch_output_path(self, output_path, batch_index):
        if batch_index == 1:
            return output_path
        return output_path.with_name(f"{output_path.stem}_{batch_index:03d}{output_path.suffix}")

    def _build_batch_header_text(self, header_text, batch_index, batch_count):
        if not header_text:
            return None
        return f"{header_text}\n\nBatch: {batch_index}/{batch_count}"

    def _stage_batch_files(self, root_dir, stage_dir, files):
        root_path = Path(root_dir)
        stage_path = Path(stage_dir)
        for file_info in files:
            source_path = root_path / file_info["rel_path"]
            target_path = stage_path / file_info["rel_path"]
            target_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(source_path, target_path)
            except OSError:
                shutil.copy2(source_path, target_path)

    def _summarize_security(self, security_values):
        if not security_values:
            return "Unknown"
        unique_values = set(security_values)
        if len(unique_values) == 1:
            return security_values[0]
        return "Mixed"

    def _write_batch_index(self, run_folder, output_name, planning, aggregate):
        index_path = Path(run_folder) / "index.md"
        with open(index_path, "w", encoding="utf-8") as handle:
            handle.write("# Local Batch Index\n\n")
            handle.write(f"- Primary output: {output_name}\n")
            handle.write(f"- Batches: {planning['batch_count']}\n")
            handle.write(f"- Effective split size: {planning['effective_split_size']}MB\n")
            handle.write(f"- Estimated included size: {planning['estimated_total_size_mb']}MB\n")
            handle.write(f"- Largest included file: {planning['largest_file_path']} ({planning['largest_file_size_mb']}MB)\n")
            handle.write(f"- Total tokens: {aggregate['total_tokens']}\n\n")
            handle.write("## Batch Files\n\n")
            for batch, batch_output in zip(planning["batches"], aggregate["batch_outputs"]):
                handle.write(
                    f"- {batch_output} - {batch['file_count']} files, "
                    f"~{batch['estimated_size_mb']}MB, starts with {batch['first_file']}\n"
                )
        return str(index_path)

    def _orchestrate_binaries(self, root_dir, run_folder, extra_ignores):
        count = 0
        found_files = []
        for path in self._iter_collectable_binaries(root_dir, extra_ignores):
            rel_path = path.relative_to(root_dir)

            dest_name = str(rel_path).replace(os.sep, "_")
            dest_path = Path(run_folder) / dest_name
            shutil.copy2(path, dest_path)

            count += 1
            found_files.append(str(rel_path))
        
        return {"count": count, "files": found_files}

    def _iter_collectable_binaries(self, root_dir, extra_ignores=None):
        root_path = Path(root_dir)
        ignore_patterns = list(DEFAULT_IGNORE_PATTERNS)
        if extra_ignores:
            ignore_patterns.extend(extra_ignores)

        for current_root, dirnames, filenames in os.walk(root_path):
            current_root_path = Path(current_root)
            dirnames[:] = [
                dirname
                for dirname in dirnames
                if not self._matches_patterns(
                    (current_root_path / dirname).relative_to(root_path).as_posix() + "/",
                    ignore_patterns,
                )
            ]

            for filename in filenames:
                file_path = current_root_path / filename
                rel_path = file_path.relative_to(root_path).as_posix()
                if self._matches_patterns(rel_path, ignore_patterns):
                    continue
                if file_path.suffix.lower() in COLLECTABLE_BINARIES:
                    yield file_path

    def process_remote_git(self, url, output_file, extra_ignores=None, include_patterns=None, 
                           style="markdown", split_size=None, header_text=None,
                           max_tokens=None):
        effective_split_size = self._apply_token_split_limit(split_size, max_tokens)

        if split_size and effective_split_size is not None and effective_split_size < split_size:
            self.log(
                f"Applying token-based split target: {effective_split_size}MB "
                f"(from max_tokens={max_tokens})."
            )

        return self.git_processor.process_remote(url, output_file, extra_ignores, 
                                               include_patterns, style, effective_split_size, header_text)

    def crawl_website(self, url, output_file, max_pages=20):
        return self.web_processor.crawl_website(url, output_file, max_pages)

    def is_git_url(self, url):
        return self.git_processor.is_git_url(url)
