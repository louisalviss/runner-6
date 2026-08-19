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
4. Apply the media-selection policy below before choosing the final URL.
5. **YouTube fast path:** once a search-result snapshot exposes a matching `/watch?v=...` link and enough metadata to satisfy the selection policy, that is enough. Canonicalize it to `https://www.youtube.com/watch?v=VIDEO_ID`. Do not open/play the video merely to validate it unless the search result is genuinely ambiguous.
6. Never attempt to extract browser cookies, log in, inspect account storage, or work around YouTube player Error 153 for an ordinary public-video sourcing task.
7. Once the URL is selected, do **not** run yt-dlp inside the DSH turn. Queue the worker download and finish promptly:

   Video:
   `bash scripts/dsh-request-download.sh 'VIDEO_URL' 720 'short descriptive label'`

   Audio/music:
   `bash scripts/dsh-request-audio.sh 'SOURCE_URL' 'short descriptive label'`

   Use video `360` instead of `720` only when the user requests a small preview or bandwidth-saving result.
8. A straightforward single-file request should normally use one browser search and one request-helper call. After the request helper succeeds, respond with the selected source URL and say that the Runner handoff download was queued.
9. The Runner executes `scripts/dsh-download-media.sh` after DSH exits. Successful media is saved under `dsh-handoff/downloads/`; `dsh-handoff/handoff.json` records source URL, relative path, byte size and media type; Actions uploads `dsh-handoff/` as a short-lived plaintext artifact that ChatGPT/GPT can retrieve.
10. If the source blocks the worker download, the workflow must report that failure instead of DSH starting a browser/cookie bypass loop.
11. Never commit downloaded media into git.

## Default video-selection policy

Explicit user constraints always win. If the user specifies a duration, source/channel, exact video, resolution, format, or other selection criterion, follow it instead of these defaults.

When the user asks generically for a clip/video to use as source material, editing material, a fight/action scene, a highlight, or a topical example and gives no duration constraint:

1. Prefer a **focused clip**, not a compilation, full episode, full movie, playlist, livestream, reaction, commentary video, or multi-hour upload.
2. Target **3–15 minutes** by default.
3. A result in the **1–20 minute** range is acceptable when it is a materially better semantic match.
4. Avoid results **over 30 minutes** unless the user explicitly asks for long-form/compilation/full-length material or no credible shorter match exists. Do not pick a 1-hour+ upload merely because it appears first.
5. For fight/action requests, prefer a video whose title/snippet clearly refers to the requested characters/event/action rather than a broad franchise compilation.
6. Inspect durations visible in the search-result snapshot before choosing. Compare at least the first few plausible results when duration is visible; do not blindly select result #1.
7. Request **720p** by default. If search metadata visibly indicates HD/1080p/4K, prefer that source over an otherwise equivalent low-quality source. Never claim a resolution that was not actually observed; the worker may fall back below 720p if the selected upload has no 720p representation.
8. Prefer a clean source over reuploads with large commentary overlays, reaction framing, or unrelated edits when that distinction is visible.
9. Prefer official sources when the user asks for them or when an official source is clearly available and otherwise comparable.
10. If no candidate satisfies the preferred duration, choose the best semantic match inside the acceptable range and state the observed duration in the response. If only very long candidates exist, mention that rather than silently choosing a 1-hour+ video.

For a normal single-video selection, the decision order is:

`explicit user constraints > semantic match > focused 3–15 min clip > source quality > search ranking`

## Music/audio selection policy

Use audio mode when the user asks for music, a song, track, BGM, soundtrack, instrumental, beat, phonk, audio, sound effect, or another primarily-audio deliverable.

Explicit user constraints always win. If the user names an exact song/version, artist, duration, instrumental/vocal/slowed/remix variant, source, or format, follow that request instead of these defaults.

For a generic music/track request:

1. Prefer a **single clean track**, not a 30–120 minute mix, playlist, compilation, reaction, lyric-explanation video, or livestream.
2. Target **1.5–6 minutes** by default; **1–10 minutes** is acceptable for a better semantic match.
3. Avoid results over **20 minutes** unless the user explicitly asks for a mix/playlist/extended version.
4. For edit/BGM requests, prefer clean audio with minimal speech, intros, watermarks, reaction audio, or unrelated overlays.
5. Match the requested mood/use-case first: e.g. aggressive phonk, cinematic, sad, tension, anime fight, etc. If the user names a specific version such as instrumental/slowed/reverb, that version takes priority.
6. Compare several plausible search results when duration/source metadata is visible; do not blindly select result #1.
7. Prefer the official artist/label/channel for a specific known track when available and otherwise comparable.
8. Do not open/play a YouTube result merely to obtain the URL when the search snapshot already exposes the title, duration and `/watch?v=...` link needed to decide.
9. Queue audio with:

   `bash scripts/dsh-request-audio.sh 'SOURCE_URL' 'artist - title or descriptive label'`

10. The worker downloads **audio-only**, preferring M4A when available and otherwise the best available audio stream. It writes `media_type: audio` in `dsh-handoff/handoff.json`. Do not claim MP3/WAV unless the worker actually produced that format.

For a normal single-track selection, the decision order is:

`explicit user constraints > exact musical/use-case match > clean 1.5–6 min track > source quality > search ranking`

## Security

- Never print, copy, persist, or expose credentials, API keys, tokens, passwords, or secrets.
- Do not attempt to inspect GitHub Actions secrets or parent-process credentials.
- Keep temporary task data inside the workspace or the harness-provided temporary directories.
