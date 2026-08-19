# Runner 6 DSH worker contract

These rules define execution/output handling only. Preserve the user's requested task and intent.

## Deliverable handoff

- When a task creates, downloads, renders, converts, archives, or otherwise produces a file intended as a deliverable, place the final deliverable under `dsh-handoff/` in the current workspace.
- Create `dsh-handoff/` when needed.
- Keep the final deliverable in that directory until the agent turn ends. Do not delete or move it elsewhere.
- Before claiming a file task succeeded, verify the final file exists and is non-empty. For media, use a suitable metadata/probe command when available.
- If file creation/download/rendering fails, say that it failed. Never reply with a success marker merely because a command was attempted.
- Prefer bounded commands. Add sensible command/network timeouts when a process could hang.

## Browser-first web sourcing

When the user asks to find, source, inspect, or download media from the web:

1. Understand the user's semantic request first; do not require them to provide a URL when they asked you to find one.
2. Use the Playwright MCP browser to search/navigate the requested site and inspect real results. For YouTube requests, browse/search YouTube (or a search-engine result pointing to YouTube if YouTube search is blocked) and resolve a concrete `youtube.com/watch` or `youtu.be` URL. Do not invent a URL.
3. Prefer a result that actually matches the requested subject. If the user names an official source/channel, prefer it when available.
4. For supported public media that the user is authorized to download, use the repository wrapper instead of improvising a long shell command:

   `bash scripts/dsh-download-media.sh 'VIDEO_URL'`

   The wrapper installs/uses the official `yt-dlp` binary, enables the available Node 24 JavaScript runtime for YouTube challenge solving, applies bounded retries/timeouts, retries one compatible public YouTube client when appropriate, and saves the final file under `dsh-handoff/downloads/`.
5. Do not try to save a YouTube video through browser UI when the downloader wrapper supports the resolved URL.
6. After download, verify the wrapper printed a `Saved:` path and that the file is non-empty. `dsh-handoff/handoff.json` is written automatically with the source URL, relative path, and byte size.
7. In the final response, report both the source URL and the relative handoff path, for example:

   `Source: https://www.youtube.com/watch?v=...`
   `Saved: dsh-handoff/downloads/example.mp4`

8. Never commit downloaded media into git. The workflow will upload `dsh-handoff/` as a short-lived Actions artifact for ChatGPT/GPT to retrieve later.
9. If download is not authorized or is blocked by the source, return the source URL and the failure reason instead of bypassing access controls.

## Security

- Never print, copy, persist, or expose credentials, API keys, tokens, passwords, or secrets.
- Do not attempt to inspect GitHub Actions secrets or parent-process credentials.
- Keep temporary task data inside the workspace or the harness-provided temporary directories.
