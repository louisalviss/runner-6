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
4. For supported public media that the user is authorized to download, use `yt-dlp` rather than trying to save the media through the browser UI.
5. Save downloadable media under `dsh-handoff/downloads/` so the GitHub Actions artifact collector can hand it to ChatGPT/GPT later.
6. For a single public YouTube video, a good bounded default is:

   `timeout 150s yt-dlp --js-runtimes node --no-playlist --restrict-filenames --socket-timeout 20 --retries 3 -P dsh-handoff/downloads -o '%(title).100s_[%(id)s].%(ext)s' -f 'best[height<=720][ext=mp4]/best[height<=720]/best' 'VIDEO_URL'`

   If YouTube's default client returns a GVS/PO-token 403, retry a compatible public client/format rather than looping indefinitely. Do not use account cookies unless the user has explicitly configured an authorized browser session for that purpose.
7. After download, verify the final file exists and is non-empty. Use `file`, `stat`, or another available probe. Do not claim success without verification.
8. In the final response, report both the source URL and the relative handoff path, for example:

   `Source: https://www.youtube.com/watch?v=...`
   `Saved: dsh-handoff/downloads/example.mp4`

9. Never commit downloaded media into git. The workflow will upload `dsh-handoff/` as a short-lived Actions artifact.

## Security

- Never print, copy, persist, or expose credentials, API keys, tokens, passwords, or secrets.
- Do not attempt to inspect GitHub Actions secrets or parent-process credentials.
- Keep temporary task data inside the workspace or the harness-provided temporary directories.
