import subprocess
import re
from pathlib import Path
from .base import BaseProcessor
from .config import REPOMIX_CMD, DEFAULT_IGNORE_PATTERNS

class GitProcessor(BaseProcessor):
    def process_remote(self, url, output_file, extra_ignores=None, include_patterns=None, 
                       style="markdown", split_size=None, header_text=None):
        """Processes a remote Git repository using Repomix --remote."""
        cmd = list(REPOMIX_CMD) + ["--remote", url, "--output", output_file, "--style", style]
        
        all_ignores = list(DEFAULT_IGNORE_PATTERNS)
        if extra_ignores:
            all_ignores.extend(extra_ignores)
        cmd.extend(["--ignore", ",".join(all_ignores)])
            
        if include_patterns:
            normalized = []
            for p in include_patterns:
                if "." not in p and "*" not in p:
                    normalized.append(f"**/*.{p}")
                else:
                    normalized.append(p)
            cmd.extend(["--include", ",".join(normalized)])

        if split_size:
            cmd.extend(["--split-output", f"{split_size}mb"])
            
        if header_text:
            cmd.extend(["--header-text", header_text])

        self.log(f"Running Repomix Remote: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            stdout = result.stdout
            self.log("Repomix Remote completed successfully.")
            
            stats = {
                "total_processed": 0,
                "total_tokens": 0,
                "total_chars": 0,
                "security": "Unknown",
                "top_files": []
            }
            
            files_match = re.search(r"Total Files:\s+(\d+)", stdout)
            tokens_match = re.search(r"Total Tokens:\s+([\d,]+)", stdout)
            chars_match = re.search(r"Total Chars:\s+([\d,]+)", stdout) or re.search(r"Total Characters:\s+([\d,]+)", stdout)
            
            if files_match: stats["total_processed"] = int(files_match.group(1))
            if tokens_match: stats["total_tokens"] = int(tokens_match.group(1).replace(",", ""))
            if chars_match: stats["total_chars"] = int(chars_match.group(1).replace(",", ""))
            
            top_files_section = re.search(r"Top 5 Files by Token Count:.*?\n(.*?)\n\n", stdout, re.DOTALL)
            if top_files_section:
                entries = re.findall(r"\d+\.\s+(.+?)\s+\(([\d,]+)\s+tokens", top_files_section.group(1))
                stats["top_files"] = [{"path": e[0], "tokens": e[1]} for e in entries]

            security_match = re.search(r"Security Check:.*?\n\s*([✔✖])\s+(.+)", stdout)
            if security_match:
                stats["security"] = security_match.group(2)

            # 3. Word Count Calculation
            stats["total_words"] = self._count_total_words(output_file)

            return stats
            
        except subprocess.CalledProcessError as e:
            self.log(f"Repomix Remote Error: {e.stderr}")
            raise RuntimeError(f"Repomix Remote failed: {e.stderr}")

    def _count_total_words(self, output_file):
        """Counts words in primary output and all split files."""
        total_words = 0
        output_path = Path(output_file)
        base_name = output_path.stem
        ext = output_path.suffix
        directory = output_path.parent
        
        found_files = []
        for file in directory.iterdir():
            if file.name == output_path.name or (file.stem.startswith(f"{base_name}.") and file.suffix == ext):
                found_files.append(file)
                
        for file_path in found_files:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    total_words += len(content.split())
            except Exception as e:
                self.log(f"Warning: Could not count words in {file_path}: {e}")
                
        return total_words

    def is_git_url(self, url):
        return url.startswith(('http://', 'https://', 'git@')) and (url.endswith('.git') or 'github.com' in url or 'gitlab.com' in url)
