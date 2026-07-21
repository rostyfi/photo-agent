# rescan-display

> **Status:** Draft
> **Created:** 2026-06-04 17:22:31

## Overview

Give the **"Rescan folder"** button visual feedback when a scan is in progress by changing its label to **"Scanning…"** and disabling it until the callback completes.

## Motivation

Folder scans on large directories can take a noticeable amount of time (recursive walk + WAL/DB lookups). Right now the button gives no feedback, so users may click it multiple times or think the app is frozen.

## Requirements

- **R1:** While `update_folder_list` callback is running, the **"Rescan folder"** button text changes to **"Scanning…"** and the button becomes disabled.
- **R2:** When the callback finishes, the button text reverts to **"Rescan folder"** and the button is enabled again.
- **R3:** The existing folder list, pending count, and `folder-cache` outputs must still update normally.

## Design / Approach

Use Dash's `running` keyword argument in the existing `@app.callback` decorator. This feature is already used by the processing callbacks; we will apply the same pattern to `register_folder_callback`.

### Files to modify

```
src/callbacks.py   - Add running=[(Output("btn-rescan", "disabled"), True, False),
                                (Output("btn-rescan", "children"), "Scanning…", "Rescan folder")]
                     to the update_folder_list callback decorator.
```

### API changes (if any)

None.

## Implementation Steps

1. Edit `src/callbacks.py::register_folder_callback` — add `running` argument to the `@app.callback` decorator.
2. Run `python -m pytest tests/test_layout.py` to ensure no layout regressions (button ID `btn-rescan` already exists).
3. Manual smoke test: load the UI, pick a large folder, click **"Rescan folder"**, verify the label changes and reverts.

## Testing Plan

- [ ] `tests/test_layout.py` still passes (`btn-rescan` ID present).
- [ ] Manual smoke test: label toggles correctly.

## Edge Cases & Risks

- Concurrent clicks are prevented naturally because Dash disables the button for the duration of the callback.
- No changes to batch-processing logic; risk is minimal.
