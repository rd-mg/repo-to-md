
# Limits
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_TOTAL_FILES = 2000
MAX_TREE_LINES = 500
MAX_TOKENS_PER_FILE = 500000  # Transitioning from words to tokens

# File Categorization
MANIFEST_NAMES = [
    'package.json', 'requirements.txt', 'go.mod', 'Cargo.toml', 
    'pyproject.toml', 'setup.py', 'composer.json', 'Gemfile'
]

EDITABLE_EXTENSIONS = [
    'md', 'py', 'js', 'ts', 'go', 'rs', 'java', 'c', 'cpp', 'h', 'hpp', 
    'yaml', 'yml', 'xml', 'json', 'txt', 'sh', 'ps1', 'css', 'html', 
    'sql', 'csv', 'toml', 'ini', 'dockerfile', 'rst'
]

DEFAULT_SELECTED_EXTENSIONS = ['md', 'py', 'js', 'ts', 'go', 'yaml', 'yml', 'json', 'txt', 'rst']

ODOO_SELECTED_EXTENSIONS = ['py', 'xml', 'csv', 'js', 'md', 'json', 'yaml', 'yml', 'txt', 'rst', 'html', 'css', 'scss']

ENTRY_NAMES = [
    'main.py', 'app.py', 'index.ts', 'index.js', 'app.ts', 'app.js', 
    'main.ts', 'main.go', 'server.js', 'server.ts', '__manifest__.py'
]

# Binary Extensions to skip (Strictly ignored by Repomix)
BINARY_EXTENSIONS = {
    '.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.bin', 
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', 
    '.pdf', '.zip', '.tar.gz', '.rar', '.7z', '.mp4', '.mov', 
    '.mp3', '.wav', '.flac', '.ogg', '.m4a', '.ttf', '.otf', 
    '.woff', '.woff2', '.eot', '.psd', '.ai', '.sqlite', '.db',
    '.avif', '.bmp', '.jp2', '.tif', '.tiff', '.heic', '.heif'
}

# Collectable Binaries (Copied to output folder and shadowed in pack)
# These are types supported by NotebookLM as separate uploads
COLLECTABLE_BINARIES = {
    '.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.ico',
    '.avif', '.bmp', '.jp2', '.tif', '.tiff', '.heic', '.heif',
    '.mp3', '.wav', '.mp4', '.mov', '.ogg', '.m4a'
}

BINARY_REF_SUFFIX = ".bin_ref.txt"

# Default Ignore Patterns
DEFAULT_IGNORE_PATTERNS = [
    'node_modules/**', '.git/**', '.venv/**', '__pycache__/**', 
    '*.pyc', '.env', '.DS_Store', 'md-created/**', 'repomix-output.*',
    '**/.*', '**/__*'
]

# Repomix Command
REPOMIX_CMD = ["/home/rdmachadog/.bun/bin/bun", "x", "repomix"]

# NotebookLM & LLM Best Practices
DEFAULT_MAX_SPLIT_SIZE_MB = 200
DEFAULT_MAX_TOKENS = 500000

ODOO_HEADER_TEMPLATE = """This file is a Repository Digest optimized for Odoo Development.
Repository: {repo_name}
Date: {date}

Context:
This file (.txt) contains a packed Odoo repository. It uses an internal XML-like structure for file separation.

Odoo Specific Rules:
1. **__manifest__.py**: Always check this first for module dependencies and data file load order.
2. **Models (_inherit / _inherits)**: Pay close attention to how models extend core Odoo functionality.
3. **Views (XPath)**: XML files use XPath to modify existing views. Precision in these paths is critical.
4. **Security**: 'ir.model.access.csv' defines the permissions for all models.
5. **OWL (Odoo Web Library)**: JS files often contain OWL components (ES6 classes).

Instructions:
- Use the internal tags (<file_path>) to identify files.
- Prioritize understanding the 'depends' list in manifests to build the dependency tree.
- Analyze 'inherit' patterns to identify if a module is creating new logic or extending existing ones.
"""

NOTEBOOKLM_HEADER_TEMPLATE = """This file is a Repository Digest optimized for LLM analysis.
Repository: {repo_name}
Date: {date}

Context: 
This file (.txt) is a container for a packed repository. It uses an internal XML structure for maximum precision.

Instructions:
1. Parse the internal XML tags to identify file paths and contents.
2. Even though this container is .txt, treat internal code according to its original extension.
3. Binary files (Images, PDFs) are referenced via '.bin_ref.txt' placeholders and provided as separate uploads in this session.
"""
