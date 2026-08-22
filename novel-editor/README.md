# Novel Editor Pipeline

Dedicated pipeline for AI-assisted novel cleanup and EPUB generation.

Flow:
- Import source EPUB/TXT
- Split chapters
- Build Story Bible
- AI editing with Cloudflare Workers AI
- Consistency verification
- Export EPUB

Initial phase: benchmark 3 chapters before full processing.
