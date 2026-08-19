# Runner 6 DSH worker contract

These rules define execution/output handling only. Preserve the user's requested task and intent.

## Deliverable handoff

- User deliverables belong under `dsh-handoff/` in the current workspace. Browser diagnostic snapshots/logs do not.
- The GitHub Actions worker, not the language-model turn, performs queued media downloads after DSH returns.
- Before claiming a file task succeeded, only claim the URL was selected/queued unless you have actually observed the final downloaded file. The workflow will append the real artifact/file information to the result after download execution.
- Prefer bounded tool work. Do not spend the whole agent turn retrying a blocked player, login, cookie, or download path.

## Browser-first web sourcing

When the user asks to find, source, inspect, or download media from the web:

1. Understand the semantic request first. Do not require the user to provide a URL when they asked you to find one.
2. Use the Playwright MCP browser to search/navigate the requested site and inspect real results. For YouTube requests, search YouTube (or a search-engine result pointing to YouTube if YouTube search is blocked) and resolve a concrete `youtube.com/watch` or `youtu.be` URL. Never invent a URL.
3. Prefer a result that matches the requested subject. If the user names an official source/channel, prefer it when available.
4. **YouTube fast path:** once a search-result snapshot exposes a matching `/watch?v=...` link, that is enough. Canonicalize it to `https://www.youtube.com/watch?v=VIDEO_ID`. Do not open/play the video merely to validate it unless the search result is genuinely ambiguous.
5. Never attempt to extract browser cookies, log in, inspect account storage, or work around YouTube player Error 153 for an ordinary public-video sourcing task.
6. Once the URL is selected, do **not** run yt-dlp inside the DSH turn. Queue the worker download and finish promptly:

   `bash scripts/dsh-request-download.sh 'VIDEO_URL' 720 'short descriptive label'`

   Use `360` instead of `720` when a small preview is sufficient.
7. A straightforward single-video request should normally use one browser search and one `dsh-request-download.sh` call. After the request script succeeds, respond with the selected source URL and say that the Runner handoff download was queued.
8. The Runner executes `scripts/dsh-download-media.sh` after DSH exits. Successful media is saved under `dsh-handoff/downloads/`; `dsh-handoff/handoff.json` records source URL, relative path and byte size; Actions uploads `dsh-handoff/` as a short-lived plaintext artifact that ChatGPT/GPT can retrieve.
9. If the source blocks the worker download, the workflow must report that failure instead of DSH starting a browser/cookie bypass loop.
10. Never commit downloaded media into git.

## Security

- Never print, copy, persist, or expose credentials, API keys, tokens, passwords, or secrets.
- Do not attempt to inspect GitHub Actions secrets or parent-process credentials.
- Keep temporary task data inside the workspace or the harness-provided temporary directories.
