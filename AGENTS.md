# Runner 6 DSH worker contract

These rules define execution/output handling only. Preserve the user's requested task and intent.

## Deliverable handoff

- When a task creates, downloads, renders, converts, archives, or otherwise produces a file intended as a deliverable, place the final deliverable under `dsh-handoff/` in the current workspace.
- Create `dsh-handoff/` when needed.
- Keep the final deliverable in that directory until the agent turn ends. Do not delete or move it elsewhere.
- Before claiming a file task succeeded, verify the final file exists and is non-empty. For media, use a suitable metadata/probe command when available.
- If file creation/download/rendering fails, say that it failed. Never reply with a success marker merely because a command was attempted.
- Prefer bounded commands. Add sensible command/network timeouts when a process could hang.

## Security

- Never print, copy, persist, or expose credentials, API keys, tokens, passwords, or secrets.
- Do not attempt to inspect GitHub Actions secrets or parent-process credentials.
- Keep temporary task data inside the workspace or the harness-provided temporary directories.
