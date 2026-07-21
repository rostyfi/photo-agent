# sidecar-isolation

> **Status:** Draft  
> **Created:** 2026-05-31 16:11:38

## Overview

Refactor the sidecar subsystem so that it is fully isolated behind an abstract interface. Consumers (`discovery`, `saver`, `strategy`) must depend on a contract (`AbstractSidecarStore`), not on the concrete `SidecarWriter` class or the module-level singleton `get_writer()`.

## Motivation

Today `SidecarWriter` and its global singleton leak into `discovery.py`, `saver.py`, and `strategy.py`. This makes the subsystem hard to mock in tests and hard to swap or extend (e.g. a future remote-store backend would require touching every consumer). We want clean boundaries: the sidecar module exposes an interface; consumers receive an instance via constructor injection.

## Requirements

1. **Introduce `AbstractSidecarStore`** — an ABC in `src/sidecar/store.py` defining the contract:
   - `save(image_path: str, result: Dict) -> str`
   - `load(image_path: str) -> Optional[Dict]`
   - `exists(image_path: str) -> bool`
   - `sidecar_path(image_path: str) -> Path` (classmethod — pure computation, no state)
2. **Make `SidecarWriter` implement the interface** — update `src/sidecar.py` so `SidecarWriter(AbstractSidecarStore)`.
3. **Type the singleton** — `get_writer()` must return `AbstractSidecarStore`, not the concrete class.
4. **Constructor injection in savers** — `SidecarResultSaver.__init__(self, store: Optional[AbstractSidecarStore] = None)` defaults to `get_writer()`. `CollectingSidecarSaver` inherits the same.
5. **Constructor injection in strategy** — `WALSequentialStrategy.__init__(...)` gains `sidecar_store: Optional[AbstractSidecarStore] = None` defaulting to `get_writer()`.
6. **Decouple discovery** — `PhotoList._load_processed_set()` must use `get_writer()` (typed as the interface) instead of directly importing `SidecarWriter`.
7. **Zero external effect** — sidecar JSON paths, file contents, `.open-photo-agent` directory layout, CLI behavior, and UI behavior must remain identical.

## Design / Approach

### Before

```
src/sidecar.py           ── SidecarWriter (concrete) + get_writer() singleton
     │
     ├── src/discovery.py          imports SidecarWriter directly
     ├── src/coordinator/saver.py imports get_writer()
     └── src/coordinator/strategy.py imports get_writer()
```

### After

```
src/sidecar/
    __init__.py          ── re-exports AbstractSidecarStore, SidecarWriter, get_writer
    store.py             ── AbstractSidecarStore (ABC)
    writer.py            ── SidecarWriter (implements ABC)
src/discovery.py          ── uses AbstractSidecarStore via get_writer()
src/coordinator/saver.py  ── receives store via __init__
src/coordinator/strategy.py ── receives store via __init__
```

### Files to modify

```
src/sidecar/store.py            - NEW: AbstractSidecarStore ABC
src/sidecar/__init__.py         - NEW: package init, re-exports, get_writer() singleton
src/sidecar.py                  - REDUCE to thin compatibility shim or remove after migration
src/coordinator/saver.py        - Accept store via constructor
src/coordinator/strategy.py     - Accept store via constructor
src/discovery.py                - Import from src.sidecar package, use interface
```

## Implementation Steps

1. Create `src/sidecar/store.py` with `AbstractSidecarStore` ABC.
2. Move `SidecarWriter` implementation to `src/sidecar/writer.py` (or keep in `src/sidecar.py` temporarily) and make it inherit from `AbstractSidecarStore`.
3. Create `src/sidecar/__init__.py` that exports `AbstractSidecarStore`, `SidecarWriter`, and hosts the `get_writer()` singleton typed to `AbstractSidecarStore`.
4. Update `src/coordinator/saver.py`:
   - Add `store: Optional[AbstractSidecarStore] = None` to `SidecarResultSaver.__init__`
   - Default: `self._store = store or get_writer()`
5. Update `src/coordinator/strategy.py`:
   - Add `sidecar_store: Optional[AbstractSidecarStore] = None` to `WALSequentialStrategy.__init__`
   - Default: `self._sidecar_store = sidecar_store or get_writer()`
6. Update `src/discovery.py`:
   - Change `from src.sidecar import SidecarWriter` to `from src.sidecar import AbstractSidecarStore, get_writer`
   - In `_load_processed_set`, call `store = get_writer()` and use `store.load()` / `store.sidecar_path()` instead of `SidecarWriter.load()` / `SidecarWriter.sidecar_path()`
7. Run `python -m py_compile` on all changed files.
8. Manual smoke test: run dry-run against a folder and verify `.open-photo-agent/data/*.json` still appears in the same place with the same content.

## Testing Plan

- [ ] `python -m py_compile` passes for all modified files.
- [ ] Unit tests for `SidecarWriter` remain valid (if they import the concrete class, path may change to `src.sidecar.writer.SidecarWriter`).
- [ ] Manual smoke test: process a folder via UI (dry-run or live), verify sidecars are written to the same paths.
- [ ] Manual smoke test: rescan a folder with "exclude processed" — already-processed images are still correctly skipped.

## Edge Cases & Risks

- **Circular imports**: `src/sidecar/__init__.py` must not import heavy submodules at top level if `discovery.py` imports it during startup. Use lazy imports inside `get_writer()` or keep the writer module lightweight.
- **Default argument compatibility**: Adding optional `store` parameters to `__init__` preserves all existing call sites, but we must verify no positional callers break.
- **WAL auto-migration**: `discovery.py` auto-migrates sidecars to WAL when WAL doesn't exist. That logic must continue to work unchanged after the import change.
- **File move impact**: Moving `SidecarWriter` to `src/sidecar/writer.py` could break external imports. We should keep a re-export in `src/sidecar/__init__.py` for backward compatibility.

## References

- `src/sidecar.py` — current concrete `SidecarWriter` and singleton
- `src/coordinator/saver.py` — `SidecarResultSaver` / `CollectingSidecarSaver`
- `src/coordinator/strategy.py` — `WALSequentialStrategy._sidecar_writer`
- `src/discovery.py` — `PhotoList._load_processed_set()`
