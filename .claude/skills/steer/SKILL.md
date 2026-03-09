---
name: steer
description: macOS GUI automation CLI. Use steer to see the screen, click elements, type text, send hotkeys, scroll, drag, manage windows and apps, run OCR on Electron apps, and wait for UI conditions.
---

# Steer — macOS GUI Automation

Binary: `apps/steer/.build/release/steer`

Run `steer --help` and `steer help <command>` to learn each command's flags before using it.

## ⚠️ If `steer` is not available

If `steer` is not installed or `command not found`, use the **Native macOS Toolkit** below instead. These tools are always available and cover most of the same capabilities.

### Native macOS Toolkit (AppleScript + shell)

**Launch / activate apps:**
```bash
osascript -e 'tell application "Safari" to activate'
open -a Safari
open -a Safari "https://news.ycombinator.com"
```

**Navigate to a URL in Safari:**
```bash
osascript -e 'tell application "Safari" to set URL of front document to "https://example.com"'
# Or open a new window:
osascript -e 'tell application "Safari" to open location "https://example.com"'
```

**Wait for page load:**
```bash
# Poll until Safari is not loading
for i in $(seq 1 30); do
  loading=$(osascript -e 'tell application "Safari" to return loading of front document')
  [ "$loading" = "false" ] && break
  sleep 1
done
```

**Take a screenshot:**
```bash
screencapture -x /tmp/screenshot.png          # full screen, silent
screencapture -x -R 0,0,1920,1080 /tmp/s.png  # region
```

**Read clipboard / write clipboard:**
```bash
pbpaste                    # read
echo "text" | pbcopy       # write
```

**Type text into focused app:**
```bash
osascript -e 'tell application "System Events" to keystroke "hello world"'
```

**Press keys / hotkeys:**
```bash
osascript -e 'tell application "System Events" to keystroke "a" using command down'  # Cmd+A
osascript -e 'tell application "System Events" to key code 36'                        # Return (key code 36)
osascript -e 'tell application "System Events" to key code 53'                        # Escape
```

**Click at coordinates:**
```bash
osascript -e 'tell application "System Events" to click at {500, 300}'
```

**Read text from screen (OCR via Vision framework):**
```bash
# Use drive to run a python one-liner:
python3 -c "
import Vision, Quartz, objc
# ... or use screencapture + a Vision script
"
# Simpler: read Safari's page source directly when dealing with web content
osascript -e 'tell application "Safari" to return source of front document'
```

**Get web page content without GUI:**
```bash
curl -s "https://example.com"
# Or from the already-open Safari page:
osascript -e 'tell application "Safari" to return source of front document'
```

**Create a Note in Notes.app:**
```bash
osascript <<'EOF'
tell application "Notes"
  activate
  set newNote to make new note at folder "Notes" with properties {name:"My Title", body:"Content here"}
end tell
EOF
```

**Check what apps are running:**
```bash
osascript -e 'tell application "System Events" to get name of every process whose background only is false'
```

### Workflow with native toolkit

The same observe-act-verify loop applies:
1. `screencapture -x /tmp/before.png` — capture state
2. Perform one action (osascript / open / curl)
3. `screencapture -x /tmp/after.png` — verify it worked
4. Read the screenshot or page source to confirm before proceeding

## Commands

| Command     | Purpose                                                                                                                                                                                                    |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `see`       | Takes a screenshot (PNG) and walks the accessibility tree. Screenshot always succeeds. Elements are best-effort — may be empty for Electron apps. Pass `--ocr` to fall back to OCR when the tree is empty. |
| `click`     | Click by element ID, label, or coordinates                                                                                                                                                                 |
| `type`      | Type text into focused element or a target                                                                                                                                                                 |
| `hotkey`    | Keyboard shortcuts (cmd+s, return, escape, etc.)                                                                                                                                                           |
| `scroll`    | Scroll up/down/left/right                                                                                                                                                                                  |
| `drag`      | Drag between elements or coordinates                                                                                                                                                                       |
| `apps`      | List, launch, or activate apps                                                                                                                                                                             |
| `screens`   | List displays with resolution and scale                                                                                                                                                                    |
| `window`    | Move, resize, minimize, fullscreen, close windows                                                                                                                                                          |
| `ocr`       | Takes a screenshot and runs Vision OCR on it. Returns text with x/y positions. Use `--store` to make results clickable (O1, O2, etc.). Use when `see` returns no elements.                                 |
| `focus`     | Show currently focused element                                                                                                                                                                             |
| `find`      | Search elements by text in latest snapshot                                                                                                                                                                 |
| `clipboard` | Read/write system clipboard                                                                                                                                                                                |
| `wait`      | Wait for app launch or element to appear                                                                                                                                                                   |

Always pass `--json` for structured output.

## How to Work

You are controlling a real macOS desktop. You cannot see anything unless you explicitly look. You cannot assume anything worked unless you verify.

### 1. Know your environment first

Before doing anything, understand the display setup, what's running, and capture the current state of every screen:

```
steer screens --json       → which monitors exist, their resolution
steer apps --json          → what apps are running
steer see --screen 0 --json  → screenshot of screen 0 (primary)
steer see --screen 1 --json  → screenshot of screen 1 (if exists)
```

Take a screenshot of **each screen** returned by `steer screens`. Read them. This gives you a baseline of the desktop before you start making changes.

### 2. Focus the app, then verify

Before interacting with any app, make sure it's the active window on the right screen:

```
steer apps activate Safari --json
steer see --app Safari --json        → verify it's in front, read the state
```

### 3. One action, then observe

**NEVER chain multiple steer commands in one bash call.** The screen changes after every action. You must look after every action.

The loop is:

1. `steer see` — look at the screen
2. Read the JSON — understand what you see
3. Do ONE action (click, type, hotkey, scroll)
4. `steer see` — look again to confirm it worked
5. Repeat

### 4. Clicking safely

Before clicking anything:

- Run `steer see --app <app> --json` to get a fresh snapshot
- Use element IDs from the snapshot (B1, T1, L3) — not coordinates when possible
- If using coordinates, they are **relative to the screenshot image**, factor in window position
- After clicking, run `steer see` again to confirm the click landed

### 5. Typing into fields

- Before typing anything: ALWAYS check focus with `steer focus --json` to confirm the right element is targeted.
  - If you're not focused on the right element, use `steer apps activate <AppName> --json` to switch apps or `steer click` to focus the correct field.
  - Then validate your focus with `steer focus --json`
- Use `steer type "text" --into T1 --json` to click-then-type in one step when targeting a specific field
- If typing into the already-focused element, just `steer type "text" --json`
- After typing, verify with `steer see` that the text appeared correctly
- For URLs in browsers: type the URL, then `steer hotkey return --json`, then `steer see` to confirm navigation

### 6. Reading content from apps

Both `see` and `ocr` save a screenshot PNG. The path is in the JSON output under `"screenshot"`. You can read this image file to visually inspect what's on screen.

**Native apps** (Safari, Finder, Terminal): `steer see --app <name> --json` gives you the accessibility tree with labeled elements. If the element list is empty, the screenshot still exists — read it or try `--ocr` to fall back.

**Electron apps** (VS Code, Slack, Notion): Accessibility trees are empty. Use OCR instead:

```
steer ocr --app "VS Code" --store --json
```

With `--store`, OCR results become clickable elements (O1, O2, etc.).

**Web pages**: Accessibility tree may be shallow. Use `steer ocr --app Safari --json` to read all visible text with positions. Use the positions to click precisely.

### 7. Waiting for things

Don't assume the UI is ready after an action. Use `steer wait` or run `steer see` in a loop:

```
steer wait --app Safari --json                     → wait for app to launch
steer wait --for "Submit" --app Safari --json      → wait for element to appear
```

### 8. Multi-monitor awareness

If there are multiple screens, coordinates and screenshots are per-screen. Always check `steer screens --json` first and use `--screen <index>` when needed.

## Element IDs

Elements from `steer see` get role-based IDs: **B** (button), **T** (text field), **S** (static text), **I** (image), **C** (checkbox), **L** (link), **M** (menu item), **O** (OCR element), etc.

IDs regenerate with each snapshot. Always use IDs from the most recent `steer see` or `steer ocr --store`.

## Rules

- **One command per bash call** — never chain steer commands
- **Always verify** — `steer see` after every action
- **Focus first** — activate the app before interacting
- **Know your screens** — check `steer screens` before clicking
- **Use `--json` always** — structured output is reliable
- **Write all files to /tmp** — never write output files into the project directory
- **Run `steer help <cmd>`** if you're unsure about a command's flags
