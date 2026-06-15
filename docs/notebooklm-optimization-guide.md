# Creating the Perfect NotebookLM Repository Digest

To maximize the performance of a Large Language Model (like NotebookLM) when analyzing a repository, you need to provide a high Signal-to-Noise Ratio (SNR) document. 

## Key Optimization Strategies

### 1. The Directory Tree
Always include a hierarchical directory tree at the very top of the document. This gives the AI a "mental map" of the project's architecture before it reads any code.

### 2. Front-Matter Metadata
Use a YAML block at the beginning to provide immediate context about the document:
```yaml
---
title: "Repository Digest: my-project"
date: 2026-03-25
branch: main
tags: [Codebase, NotebookLM, Digest]
summary: "A high-SNR digest of the my-project repository."
---
```

### 3. Global Context First
Place your `README.md` and high-level documentation immediately after the directory tree. This establishes the project's purpose and usage before the AI sees the implementation details.

### 4. Smart Filtering (Must-Omits)
To stay within word limits and reduce noise, always ignore:
-   **Lock Files**: `package-lock.json`, `yarn.lock`, etc.
-   **Minified/Map Files**: `*.min.js`, `*.map`, etc.
-   **Build Artifacts**: `dist/`, `build/`, `node_modules/`.
-   **Static Assets**: Images, PDFs, and large binary files.
-   **Recursive Bloat**: Ensure the tool's own output directory is ignored.

### 5. License Stripping
In large repositories, boilerplate license headers (like MIT or Apache) can consume thousands of valuable tokens. Stripping these from the top of source files significantly improves efficiency.

### 6. Priority Ordering
Process files in this order:
1.  `README.md` (Global Context)
2.  `package.json`, `requirements.txt`, etc. (Dependency Manifests)
3.  `main.py`, `index.ts`, etc. (Entry Points)
4.  Other source files (Implementation)

By following these patterns, you create a document that allows NotebookLM to answer complex architectural questions with much higher accuracy.
