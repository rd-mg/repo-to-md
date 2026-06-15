# Repo to MD Converter

A Python script to convert a GitHub repository (from URL or local folder) into a single Markdown file.

## Features
- **NotebookLM Optimized**: Generates high-SNR (Signal-to-Noise Ratio) digests perfect for AI analysis.
- **Front-Matter Metadata**: Includes YAML headers with title, date, branch, and summary.
- **Smart Filtering**: Automatically ignores lock files (`package-lock.json`, `yarn.lock`), minified files, map files, and build artifacts.
- **Priority Structure**: Places the directory tree and `README.md` (Global Context) at the top, followed by entry points and manifests.
- **License Stripping**: Removes boilerplate license headers from source files to save tokens.
- **Recursive Protection**: Automatically ignores its own output directory to prevent file bloat.
- **CLI & GUI**: Shared logic ensures consistent, optimized output across all interfaces.

## Installation
```bash
pip install -r requirements.txt
```

## Usage
### Local Directory
```bash
python repo_to_md.py /path/to/repo -o output.md
```

### Remote GitHub URL
```bash
python repo_to_md.py https://github.com/user/repo -o output.md
```

### Additional Ignores
```bash
python repo_to_md.py . --ignore "*.log" "node_modules"
```
