# Claude Dispatcher Terminal — VS Code Extension Design

VS Code extension that allows the Claude Dispatcher bot to open integrated terminals
in VS Code/Cursor instead of separate console windows.

## Mechanism

File-based trigger: bot writes a JSON file → extension watches it → creates integrated terminal.

**Trigger file:** `~/.claude-dispatcher/terminal.json`

```json
{
  "cwd": "E:\\gym-tracker-bot",
  "command": "claude --remote-control test",
  "title": "Claude: gym-tracker-bot",
  "timestamp": 1744360000
}
```

## Extension

**Activation:** on startup (`*`)

**Logic:**
1. On activate — create `FileSystemWatcher` on `~/.claude-dispatcher/terminal.json`
2. On file change — read JSON, validate fields
3. Check `timestamp` — skip if already processed (deduplication via last seen timestamp)
4. Create terminal via `vscode.window.createTerminal()`:
   - `name`: from `title` field
   - `cwd`: from `cwd` field
   - `shellPath`: default shell
   - After terminal is created, send the command text via `terminal.sendText(command)`
5. Show the terminal panel

**Structure:**
```
vscode-extension/
├── package.json        # Extension manifest, activation events
├── src/
│   └── extension.ts    # Single file with all logic
├── tsconfig.json
└── .vscodeignore
```

## Bot Changes

**`config.json`** — new field:
```json
{ "terminal": "vscode" }
```
Values: `"vscode"` (extension trigger file), `"console"` (default, CREATE_NEW_CONSOLE).

**`config.py`** — add `terminal: str = "console"` to Config dataclass.

**`core/session_manager.py`** — `_start_remote_windows()`:
- If `terminal == "vscode"`: write `~/.claude-dispatcher/terminal.json` and wait up to 5s
- If file not picked up in 5s or `terminal == "console"`: fallback to `CREATE_NEW_CONSOLE`
- The process is NOT managed by the bot in vscode mode — VS Code owns the terminal lifecycle
- Bot still tracks session as active; monitors by checking if process exists (by name/pid)

## Deduplication

Extension stores `lastTimestamp` in memory. Ignores trigger files with timestamp <= lastTimestamp.
Bot writes `Date.now()` as timestamp before each trigger.
