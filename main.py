import os
import tempfile
import shutil
import tkinter as tk
import webbrowser
import subprocess
from tkinter import filedialog, messagebox, scrolledtext, ttk
from logic.processor import RepositoryProcessor
from logic.config import (
    DEFAULT_MAX_SPLIT_SIZE_MB, DEFAULT_MAX_TOKENS, 
    NOTEBOOKLM_HEADER_TEMPLATE, EDITABLE_EXTENSIONS, DEFAULT_SELECTED_EXTENSIONS
)
from datetime import datetime

def get_repo_name(input_str):
    """Extracts a meaningful name from a local path or URL."""
    if not input_str:
        return "repo_context"
    if os.path.isdir(input_str) or input_str.startswith(('.', os.sep)):
        return os.path.basename(os.path.abspath(input_str)) or "root"
    
    # URL handling
    name = input_str.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repository"

class RepoToMDApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Repo to MD Converter")
        self.root.geometry("800x700")
        self.root.configure(bg="#191724") # Rose Pine Base

        self.processor = RepositoryProcessor()
        self.processor.log_callback = self.log
        self.processor.progress_callback = self.update_progress
        
        self.collect_binaries_var = tk.BooleanVar(value=True)
        self.single_file_var = tk.BooleanVar(value=False)
        self.user_edited_output = False

        self.setup_styles()
        self.create_widgets()
        
        # Add variable traces for dynamic UI
        self.format_var.trace_add("write", self.update_output_extension)
        self.path_var.trace_add("write", self.on_path_change)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colors (Rose Pine)
        self.colors = {
            "base": "#191724",
            "surface": "#1f1d2e",
            "overlay": "#26233a",
            "muted": "#6e6a86",
            "subtle": "#908caa",
            "text": "#e0def4",
            "love": "#eb6f92",
            "gold": "#f6c177",
            "rose": "#ebbcba",
            "pine": "#31748f",
            "foam": "#9ccfd8",
            "iris": "#c4a7e7",
        }

        style.configure("TFrame", background=self.colors["base"])
        style.configure("TLabel", background=self.colors["base"], foreground=self.colors["text"], font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"), foreground=self.colors["iris"])
        style.configure("Subheader.TLabel", font=("Segoe UI", 10), foreground=self.colors["subtle"])
        
        style.configure("TButton", padding=6, relief="flat", background=self.colors["overlay"], foreground=self.colors["text"])
        style.map("TButton", background=[('active', self.colors["iris"])])

    def create_widgets(self):
        # Main Container
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill="both", expand=True)

        # Header
        ttk.Label(main_frame, text="Repo to MD Converter", style="Header.TLabel").pack(anchor="w")
        ttk.Label(main_frame, text="High-SNR Markdown for LLMs (Included Files Only: Max 10MB/file, 2000 files max)", style="Subheader.TLabel").pack(anchor="w", pady=(0, 20))

        # Input Type Tabs (Using Notebook)
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="x", pady=10)

        self.tab_local = ttk.Frame(self.notebook)
        self.tab_git = ttk.Frame(self.notebook)
        self.tab_web = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_local, text=" Local / Non-Git Folder ")
        self.notebook.add(self.tab_git, text=" Git Repository ")
        self.notebook.add(self.tab_web, text=" Website ")

        # Path Input
        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill="x", pady=10)
        
        ttk.Label(path_frame, text="Path or URL:").pack(anchor="w")
        input_row = ttk.Frame(path_frame)
        input_row.pack(fill="x")
        
        self.path_var = tk.StringVar()
        self.path_entry = tk.Entry(input_row, textvariable=self.path_var, bg=self.colors["surface"], fg=self.colors["text"], insertbackground=self.colors["text"], borderwidth=1, relief="flat")
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=5)
        
        self.browse_btn = ttk.Button(input_row, text="Browse", command=self.browse_path)
        self.browse_btn.pack(side="right", padx=(5, 0))

        # Config Row
        config_frame = ttk.Frame(main_frame)
        config_frame.pack(fill="x", pady=10)

        # Output Name
        col1 = ttk.Frame(config_frame)
        col1.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ttk.Label(col1, text="Output Filename:").pack(anchor="w")
        self.output_var = tk.StringVar(value="repo_context.md")
        self.output_entry = tk.Entry(col1, textvariable=self.output_var, bg=self.colors["surface"], fg=self.colors["text"], borderwidth=1, relief="flat")
        self.output_entry.pack(fill="x", ipady=3)
        self.output_entry.bind("<Key>", self.on_output_manual_edit)

        # Ignores
        col2 = ttk.Frame(config_frame)
        col2.pack(side="left", fill="x", expand=True, padx=10)
        ttk.Label(col2, text="Extra Ignores:").pack(anchor="w")
        self.ignore_var = tk.StringVar()
        tk.Entry(col2, textvariable=self.ignore_var, bg=self.colors["surface"], fg=self.colors["text"], borderwidth=1, relief="flat").pack(fill="x", ipady=3)

        # Max Pages
        col3 = ttk.Frame(config_frame)
        col3.pack(side="left", fill="x", expand=True, padx=(10, 0))
        ttk.Label(col3, text="Max Pages (Web):").pack(anchor="w")
        self.max_pages_var = tk.StringVar(value="20")
        tk.Entry(col3, textvariable=self.max_pages_var, bg=self.colors["surface"], fg=self.colors["text"], borderwidth=1, relief="flat").pack(fill="x", ipady=3)

        # Advanced Config Row (Format & Extensions)
        adv_frame = ttk.Frame(main_frame)
        adv_frame.pack(fill="x", pady=10)

        # Output Format
        fmt_col = ttk.Frame(adv_frame)
        fmt_col.pack(side="left", padx=(0, 20))
        ttk.Label(fmt_col, text="Output Format:").pack(anchor="w")
        self.format_var = tk.StringVar(value="markdown")
        self.format_combo = ttk.Combobox(fmt_col, textvariable=self.format_var, values=["markdown", "xml", "json", "plain-text"], state="readonly", width=15)
        self.format_combo.pack(fill="x", ipady=3)

        # Extensions
        ext_col = ttk.Frame(adv_frame)
        ext_col.pack(side="left", fill="x", expand=True)
        ttk.Label(ext_col, text="Include Extensions:").pack(anchor="w")
        
        ext_grid = ttk.Frame(ext_col)
        ext_grid.pack(fill="x", pady=5)
        
        self.ext_vars = {}
        for i, ext in enumerate(EDITABLE_EXTENSIONS):
            var = tk.BooleanVar(value=(ext in DEFAULT_SELECTED_EXTENSIONS))
            self.ext_vars[ext] = var
            cb = tk.Checkbutton(ext_grid, text=f".{ext}", variable=var, bg=self.colors["base"], fg=self.colors["text"], 
                               selectcolor=self.colors["surface"], activebackground=self.colors["base"], 
                               activeforeground=self.colors["iris"], font=("Segoe UI", 9))
            cb.grid(row=i//6, column=i%6, sticky="w", padx=5)

        # Advanced Config Row 2 (Splits, Tokens, Optimization)
        adv_frame2 = ttk.Frame(main_frame)
        adv_frame2.pack(fill="x", pady=5)

        # Max Split Size
        split_col = ttk.Frame(adv_frame2)
        split_col.pack(side="left", padx=(0, 20))
        ttk.Label(split_col, text="Max File Size (MB):").pack(anchor="w")
        self.split_var = tk.StringVar(value=str(DEFAULT_MAX_SPLIT_SIZE_MB))
        tk.Entry(split_col, textvariable=self.split_var, bg=self.colors["surface"], fg=self.colors["text"], width=10).pack(fill="x", ipady=3)

        # Max Tokens
        token_col = ttk.Frame(adv_frame2)
        token_col.pack(side="left", padx=(0, 20))
        ttk.Label(token_col, text="Max Tokens/File:").pack(anchor="w")
        self.tokens_var = tk.StringVar(value=str(DEFAULT_MAX_TOKENS))
        tk.Entry(token_col, textvariable=self.tokens_var, bg=self.colors["surface"], fg=self.colors["text"], width=15).pack(fill="x", ipady=3)

        # NotebookLM Toggle
        self.notebooklm_var = tk.BooleanVar(value=False)
        self.notebooklm_cb = tk.Checkbutton(adv_frame2, text="Optimize for NotebookLM", variable=self.notebooklm_var, 
                                           bg=self.colors["base"], fg=self.colors["iris"], 
                                           selectcolor=self.colors["surface"], activebackground=self.colors["base"], 
                                           font=("Segoe UI", 10, "bold"), command=self.on_notebooklm_toggle)
        self.notebooklm_cb.pack(side="left", padx=10)

        # Binary Collection Toggle
        self.collect_binaries_cb = tk.Checkbutton(adv_frame2, text="Collect Binaries (Copy & Shadow)",
                                                variable=self.collect_binaries_var,
                                                bg=self.colors["base"], fg=self.colors["text"],
                                                selectcolor=self.colors["surface"], activebackground=self.colors["base"],
                                                font=("Segoe UI", 9))
        self.collect_binaries_cb.pack(side="left", padx=10)

        # Single File Toggle
        self.single_file_cb = tk.Checkbutton(adv_frame2, text="Single File (No Splits)",
                                             variable=self.single_file_var,
                                             bg=self.colors["base"], fg=self.colors["gold"],
                                             selectcolor=self.colors["surface"], activebackground=self.colors["base"],
                                             font=("Segoe UI", 10, "bold"))
        self.single_file_cb.pack(side="left", padx=10)

        # Action Button
        self.run_btn = tk.Button(main_frame, text="GENERATE REPO CONTEXT", command=self.start_conversion, bg=self.colors["iris"], fg=self.colors["base"], font=("Segoe UI", 12, "bold"), relief="flat", pady=10)
        self.run_btn.pack(fill="x", pady=20)

        # Progress
        self.progress = ttk.Progressbar(main_frame, mode="determinate")
        self.progress.pack(fill="x", pady=(0, 10))

        # Logs
        ttk.Label(main_frame, text="Logs:", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.log_area = scrolledtext.ScrolledText(main_frame, height=15, bg=self.colors["surface"], fg=self.colors["subtle"], borderwidth=0, font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True)
        self.log_area.config(state='disabled')

    def on_path_change(self, *args):
        if self.user_edited_output:
            return
            
        path_val = self.path_var.get().strip()
        repo_name = get_repo_name(path_val)
        
        fmt = self.format_var.get()
        if self.notebooklm_var.get() or self.odoo_var.get():
            ext = ".txt"
        else:
            ext_map = {"xml": ".xml", "markdown": ".md", "json": ".json", "plain-text": ".txt"}
            ext = ext_map.get(fmt, ".md")
            
        self.output_var.set(f"{repo_name}{ext}")

    def on_output_manual_edit(self, event):
        # Ignore modifier keys
        if event.keysym not in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R"):
            self.user_edited_output = True

    def browse_path(self):
        selected_tab = self.notebook.index(self.notebook.select())
        if selected_tab == 0: # Local / Non-Git Folder
            path = filedialog.askdirectory()
            if path: self.path_var.set(path)
        else:
            messagebox.showinfo("Hint", "Browse is only for Local Folders. For Git or Web, please paste the URL.")

    def on_notebooklm_toggle(self):
        if self.notebooklm_var.get():
            self.format_var.set("xml")
            self.split_var.set("200")
            self.tokens_var.set("500000")
            # Select common text extensions if not already
            for ext in ["py", "xml", "js", "md", "rst"]:
                if ext in self.ext_vars:
                    self.ext_vars[ext].set(True)
            # NotebookLM limit: 500k words
            self.tokens_var.set("500000")
            # Update extension immediately
            self.update_output_extension()
        
        # Also refresh name logic
        self.on_path_change()

    def update_output_extension(self, *args):
        fmt = self.format_var.get()
        current_name = self.output_var.get()
        
        if self.notebooklm_var.get():
            # For NotebookLM, we force .txt because they don't accept .xml
            new_ext = ".txt"
        else:
            ext_map = {"xml": ".xml", "markdown": ".md", "json": ".json", "plain-text": ".txt"}
            new_ext = ext_map.get(fmt, ".md")
        
        # Only update if the base name exists
        base, old_ext = os.path.splitext(current_name)
        # If it's a double extension like .xml.txt, handle it
        if base.endswith(('.xml', '.md', '.json', '.txt')):
            base = os.path.splitext(base)[0]
            
        if base:
            self.output_var.set(f"{base}{new_ext}")

    def log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, f"{message}\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.root.update_idletasks()

    def update_progress(self, value):
        self.progress["value"] = value * 100
        self.root.update_idletasks()

    def show_completion_report(self, stats, output_path, format_type):
        report = DigestReportWindow(self.root, stats, output_path, format_type, self.colors)
        self.root.wait_window(report)

    def start_conversion(self):
        path_val = self.path_var.get().strip()
        out_val = self.output_var.get() or "repo_context.md"
        ignores = [p.strip() for p in self.ignore_var.get().split(",") if p.strip()]
        selected_tab = self.notebook.index(self.notebook.select())

        if not path_val:
            messagebox.showerror("Error", "Please provide a path or URL.")
            return

        # Simple heuristic to help user if they are in the wrong tab
        if selected_tab == 0 and (path_val.startswith(('http://', 'https://')) or path_val.startswith('git@')):
             if messagebox.askyesno("Switch Tab?", "The input looks like a URL, but you are in the 'Local Folder' tab. Switch to Git/Web?"):
                 if self.processor.is_git_url(path_val):
                     self.notebook.select(1)
                     selected_tab = 1
                 else:
                     self.notebook.select(2)
                     selected_tab = 2

        self.log_area.config(state='normal')
        self.log_area.delete(1.0, tk.END)
        self.log_area.config(state='disabled')
        self.progress["value"] = 0
        
        os.makedirs("md-created", exist_ok=True)
        
        # Create a unique subfolder for this run
        run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = os.path.splitext(out_val)[0]
        run_folder = os.path.join("md-created", f"{filename_base}_{run_timestamp}")
        os.makedirs(run_folder, exist_ok=True)
        
        output_path = os.path.join(run_folder, out_val)

        try:
            stats = None
            fmt = self.format_var.get()
            selected_exts = [ext for ext, var in self.ext_vars.items() if var.get()]
            
            split_size = int(self.split_var.get() or 200)
            max_tokens = int(self.tokens_var.get() or DEFAULT_MAX_TOKENS)
            header_text = None
            if self.notebooklm_var.get():
                repo_name = get_repo_name(path_val)
                header_text = NOTEBOOKLM_HEADER_TEMPLATE.format(
                    repo_name=repo_name,
                    date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )

            if selected_tab == 0: # Local / Non-Git Folder
                if not os.path.isdir(path_val):
                    raise ValueError(f"'{path_val}' is not a valid local directory.")
                effective_split_size = None if self.single_file_var.get() else split_size
                effective_max_tokens = None if self.single_file_var.get() else max_tokens
                stats = self.processor.process_repo(path_val, output_path, ignores,
                                                  include_patterns=selected_exts, style=fmt,
                                                  split_size=effective_split_size, header_text=header_text,
                                                  collect_binaries=self.collect_binaries_var.get(),
                                                  max_tokens=effective_max_tokens)
            
            elif selected_tab == 1: # Git Repo
                if os.path.isdir(path_val) and not path_val.startswith(('http', 'git@')):
                     if messagebox.askyesno("Local Folder Detected", f"'{path_val}' is a local folder. Process it locally instead of cloning?"):
                         self.notebook.select(0)
                         stats = self.processor.process_repo(path_val, output_path, ignores, 
                                                           include_patterns=selected_exts, style=fmt,
                                                           split_size=split_size, header_text=header_text,
                                                           collect_binaries=self.collect_binaries_var.get(),
                                                           max_tokens=max_tokens)
                     else:
                         raise ValueError("Cannot clone a local directory as a remote Git repository.")
                else:
                    # New: Logic now handles cloning internally via repomix --remote
                    effective_split_size = None if self.single_file_var.get() else split_size
                    effective_max_tokens = None if self.single_file_var.get() else max_tokens
                    stats = self.processor.process_remote_git(path_val, output_path, ignores,
                                                           include_patterns=selected_exts, style=fmt,
                                                           split_size=effective_split_size, header_text=header_text,
                                                           max_tokens=effective_max_tokens)
            
            elif selected_tab == 2: # Website
                limit = int(self.max_pages_var.get() or 20)
                self.processor.crawl_website(path_val, output_path, limit)

            self.log(f"Success! Saved to {output_path}")
            self.show_completion_report(stats, output_path, fmt)
        except Exception as e:
            self.log(f"CRITICAL ERROR: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")

class DigestReportWindow(tk.Toplevel):
    def __init__(self, parent, stats, output_path, format_type, colors):
        super().__init__(parent)
        self.title("Repository Digest Report")
        self.geometry("600x550")
        self.configure(bg=colors["base"])
        self.colors = colors
        self.output_path = output_path
        
        self.transient(parent)
        self.grab_set()

        # Layout
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)

        # Header
        ttk.Label(main_frame, text="✅ DIGEST GENERATED", font=("Segoe UI", 16, "bold"), foreground=colors["iris"]).pack(pady=(0, 10))
        
        # Summary Grid
        summary_frame = tk.Frame(main_frame, bg=colors["surface"], padx=15, pady=15)
        summary_frame.pack(fill="x", pady=10)
        
        def add_stat(label, value, row, col):
            tk.Label(summary_frame, text=label, bg=colors["surface"], fg=colors["subtle"], font=("Segoe UI", 9)).grid(row=row, column=col, sticky="w", padx=5)
            tk.Label(summary_frame, text=value, bg=colors["surface"], fg=colors["text"], font=("Segoe UI", 10, "bold")).grid(row=row+1, column=col, sticky="w", padx=5, pady=(0, 10))

        add_stat("Files Processed", stats.get("total_processed", 0), 0, 0)
        add_stat("Total Tokens", f"{stats.get('total_tokens', 0):,}", 0, 1)
        add_stat("Total Words", f"{stats.get('total_words', 0):,}", 2, 0)
        add_stat("Binary Attachments", stats.get("binary_attachments", 0), 2, 1)
        add_stat("Security Check", stats.get("security", "✔ Clean"), 4, 0)
        add_stat("Planned Split", f"{stats.get('planned_split_size', 0)} MB", 4, 1)
        add_stat("Batch Count", stats.get("batch_count", 1), 6, 0)
        add_stat("Largest File", f"{stats.get('largest_included_file_mb', 0)} MB", 6, 1)

        if stats.get("largest_included_file_path"):
            detail_frame = tk.Frame(main_frame, bg=colors["base"], pady=6)
            detail_frame.pack(fill="x")
            tk.Label(
                detail_frame,
                text=f"Largest included file: {stats.get('largest_included_file_path')}",
                bg=colors["base"],
                fg=colors["subtle"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")

        if stats.get("index_file"):
            index_frame = tk.Frame(main_frame, bg=colors["base"], pady=6)
            index_frame.pack(fill="x")
            tk.Label(
                index_frame,
                text=f"Batch index: {stats.get('index_file')}",
                bg=colors["base"],
                fg=colors["pine"],
                font=("Consolas", 9),
            ).pack(anchor="w")

        # Top Files
        if stats.get("top_files"):
            ttk.Label(main_frame, text="Largest Files (Tokens):", font=("Segoe UI", 10, "bold")).pack(anchor="w")
            top_frame = tk.Frame(main_frame, bg=colors["overlay"], padx=10, pady=10)
            top_frame.pack(fill="both", expand=True, pady=5)
            
            for file in stats["top_files"][:5]:
                f_row = tk.Frame(top_frame, bg=colors["overlay"])
                f_row.pack(fill="x", pady=2)
                tk.Label(f_row, text=f"• {os.path.basename(file['path'])}", bg=colors["overlay"], fg=colors["text"], font=("Consolas", 9)).pack(side="left")
                tk.Label(f_row, text=f"{file['tokens']} tokens", bg=colors["overlay"], fg=colors["pine"], font=("Consolas", 9, "bold")).pack(side="right")

        # Output Path
        path_frame = tk.Frame(main_frame, bg=colors["base"], pady=10)
        path_frame.pack(fill="x")
        tk.Label(path_frame, text="Location:", bg=colors["base"], fg=colors["subtle"], font=("Segoe UI", 9)).pack(anchor="w")
        self.path_entry = tk.Entry(path_frame, bg=colors["surface"], fg=colors["iris"], borderwidth=0, font=("Consolas", 9))
        self.path_entry.insert(0, output_path)
        self.path_entry.config(state='readonly')
        self.path_entry.pack(fill="x", ipady=5)

        # Actions
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=20)

        ttk.Button(btn_frame, text="Open Folder", command=self.open_folder).pack(side="left", expand=True, fill="x", padx=5)
        ttk.Button(btn_frame, text="Copy Path", command=self.copy_path).pack(side="left", expand=True, fill="x", padx=5)
        tk.Button(btn_frame, text="OK", command=self.destroy, bg=colors["iris"], fg=colors["base"], relief="flat", padx=20).pack(side="left", expand=True, fill="x", padx=5)

    def open_folder(self):
        folder = os.path.dirname(os.path.abspath(self.output_path))
        try:
            if os.name == 'nt': 
                os.startfile(folder)
            elif os.name == 'posix':
                # Try xdg-open for Linux desktops
                subprocess.run(['xdg-open', folder], check=True)
            else:
                self.log(f"OS {os.name} not supported for 'Open Folder'. Path: {folder}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open folder: {str(e)}")

    def copy_path(self):
        self.clipboard_clear()
        self.clipboard_append(self.output_path)
        messagebox.showinfo("Copied", "Path copied to clipboard!")

if __name__ == "__main__":
    root = tk.Tk()
    app = RepoToMDApp(root)
    root.mainloop()
op()
h(self):
        self.clipboard_clear()
        self.clipboard_append(self.output_path)
        messagebox.showinfo("Copied", "Path copied to clipboard!")

if __name__ == "__main__":
    root = tk.Tk()
    app = RepoToMDApp(root)
    root.mainloop()
ion as e:
            messagebox.showerror("Error", f"Could not open folder: {str(e)}")

    def copy_path(self):
        self.clipboard_clear()
        self.clipboard_append(self.output_path)
        messagebox.showinfo("Copied", "Path copied to clipboard!")

if __name__ == "__main__":
    root = tk.Tk()
    app = RepoToMDApp(root)
    root.mainloop()
