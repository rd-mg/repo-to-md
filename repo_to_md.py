import os
import sys
import argparse
from datetime import datetime
from logic.processor import RepositoryProcessor
from logic.config import (
    DEFAULT_MAX_SPLIT_SIZE_MB, DEFAULT_MAX_TOKENS, 
    NOTEBOOKLM_HEADER_TEMPLATE, ODOO_HEADER_TEMPLATE, ODOO_SELECTED_EXTENSIONS
)

ODOO_EXTS = ODOO_SELECTED_EXTENSIONS

def get_repo_name(input_str):
    """Extracts a meaningful name from a local path or URL."""
    if os.path.isdir(input_str) or input_str.startswith(('.', os.sep)):
        return os.path.basename(os.path.abspath(input_str)) or "root"
    
    # URL handling
    name = input_str.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repository"

def main():
    parser = argparse.ArgumentParser(description="Convert a source into High-SNR Context for LLMs using Repomix.")
    parser.add_argument("input", help="URL of a repository, website, or path to a local directory.")
    parser.add_argument("-o", "--output", help="Output filename (default: <source_name>.<ext>).")
    parser.add_argument("--style", choices=["xml", "markdown", "json", "plain-text"], default="xml", help="Output style (default: xml).")
    parser.add_argument("--include", nargs="*", default=ODOO_EXTS, help=f"Extensions to include. Defaults: {', '.join(ODOO_EXTS)}")
    parser.add_argument("--ignore", nargs="*", help="Additional patterns to ignore.")
    parser.add_argument("--split-size", type=int, default=DEFAULT_MAX_SPLIT_SIZE_MB, help=f"Max split file size in MB (default: {DEFAULT_MAX_SPLIT_SIZE_MB}).")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS, help=f"Max tokens per file (default: {DEFAULT_MAX_TOKENS}).")
    parser.add_argument("--notebooklm", action="store_true", help="Optimize for NotebookLM (Forces XML, adds header).")
    parser.add_argument("--odoo", action="store_true", help="Odoo Optimized mode (Forces XML, adds Odoo header, preselects extensions).")
    parser.add_argument("--max-pages", type=int, default=20, help="Maximum number of web pages to crawl (default: 20).")
    parser.add_argument("--local", "--dir", action="store_true", help="Treat input as a local directory.")
    
    args = parser.parse_args()
    
    repo_name = get_repo_name(args.input)

    # Optimization Modes
    header_text = None
    if args.notebooklm:
        args.style = "xml"
        if args.split_size == DEFAULT_MAX_SPLIT_SIZE_MB:
            args.split_size = 200
        if args.max_tokens == DEFAULT_MAX_TOKENS:
            args.max_tokens = 500000
            
        header_text = NOTEBOOKLM_HEADER_TEMPLATE.format(
            repo_name=repo_name,
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    elif args.odoo:
        args.style = "xml"
        if args.split_size == DEFAULT_MAX_SPLIT_SIZE_MB:
            args.split_size = 200
        if args.max_tokens == DEFAULT_MAX_TOKENS:
            args.max_tokens = 500000
            
        header_text = ODOO_HEADER_TEMPLATE.format(
            repo_name=repo_name,
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    # Determine default output filename if not provided
    ext_map = {"xml": "xml", "markdown": "md", "json": "json", "plain-text": "txt"}
    
    # If notebooklm or odoo is enabled, we force .txt because .xml is rejected
    if args.notebooklm or args.odoo:
        ext = "txt"
    else:
        ext = ext_map.get(args.style, "xml")
        
    out_val = args.output or f"{repo_name}.{ext}"
    
    # Final safety check for NotebookLM/Odoo: handle manually provided extensions
    if (args.notebooklm or args.odoo) and not out_val.lower().endswith(('.txt', '.md')):
        out_val += ".txt"

    # Ensure main output directory exists
    os.makedirs("md-created", exist_ok=True)
    
    # Create unique subfolder for this run
    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = os.path.splitext(out_val)[0]
    run_folder = os.path.join("md-created", f"{filename_base}_{run_timestamp}")
    os.makedirs(run_folder, exist_ok=True)
    
    output_path = os.path.join(run_folder, out_val)
    
    processor = RepositoryProcessor(log_callback=print)
    
    # Priority 1: Explicit Local Directory
    if args.local or os.path.isdir(args.input):
        repo_path = args.input
        if not os.path.isdir(repo_path):
            print(f"Error: {repo_path} is not a valid directory.")
            sys.exit(1)
        print(f"Processing local directory: {repo_path}...")
        stats = processor.process_repo(repo_path, output_path, args.ignore, 
                                      include_patterns=args.include, style=args.style,
                                      split_size=args.split_size, header_text=header_text,
                                      max_tokens=args.max_tokens)
        if stats:
            print(f"Successfully generated in: {run_folder}")
            print(f"Files: {stats.get('total_processed')}, Tokens: {stats.get('total_tokens')}")
            print(
                f"Planning: split={stats.get('planned_split_size')}MB, "
                f"largest={stats.get('largest_included_file_mb')}MB"
                f" ({stats.get('largest_included_file_path')})"
            )
            if stats.get("batch_count", 1) > 1:
                print(
                    f"Batches: {stats.get('batch_count')} "
                    f"(index: {stats.get('index_file')})"
                )

    # Priority 2: Git Repository URL
    elif processor.is_git_url(args.input):
        try:
            print(f"Processing remote repository via Repomix: {args.input}...")
            stats = processor.process_remote_git(args.input, output_path, args.ignore, 
                                               include_patterns=args.include, style=args.style,
                                               split_size=args.split_size, header_text=header_text,
                                               max_tokens=args.max_tokens)
            if stats:
                print(f"Successfully generated in: {run_folder}")
                print(f"Files: {stats.get('total_processed')}, Tokens: {stats.get('total_tokens')}")
                print(f"Planning: split={stats.get('planned_split_size', args.split_size)}MB")
        except Exception as e:
            print(f"An error occurred with the repository: {str(e)}")
            sys.exit(1)
    
    # Priority 3: Web URL
    elif args.input.startswith(('http://', 'https://')):
        print(f"Starting web crawl: {args.input}...")
        pages = processor.crawl_website(args.input, output_path, args.max_pages)
        print(f"Successfully generated {output_path} with {pages} pages.")

    else:
        print(f"Error: {args.input} is not a valid directory or URL.")
        sys.exit(1)

if __name__ == "__main__":
    main()
