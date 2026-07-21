# Investigation: Metadata Not Visible After Processing

**Status:** Ready for execution  
**Created:** 2026-07-18  
**Priority:** High

## Problem Summary

User reports that while metadata extraction from JPG files works in the metadata tester, when processing photos through the normal flow and saving to the database, the metadata values are not visible later when viewing the images.

## Root Cause Analysis

### Architecture Issue: Split Database Strategy

The application has two conflicting database strategies:

1. **SequentialProcessor with folder parameter**: Creates a single `FeaturesDatabase` at the root folder's `.open-photo-agent/features.db` for metadata and embeddings
2. **DatabaseSidecarStore (singleton)**: Creates separate databases per image directory using `Path(image_path).parent`

### The Bug

In `src/sequential_processor.py`:

```python
def _save_result(self, result: ProcessingResult) -> None:
    """Save a processing result to sidecar file."""
    if result.image_path:
        data = result.as_dict()
        self._writer.save(result.image_path, data)  # Uses DatabaseSidecarStore
```

When processing images in subdirectories:
- **Metadata**: Saved to `self._db` (root folder's database) via `_extract_and_save_metadata()`
- **Extraction results**: Saved to `DatabaseSidecarStore._get_db(image_path)` (subdirectory's database)

For example, with folder `/photos` and image `/photos/vacation/img.jpg`:
- Metadata → `/photos/.open-photo-agent/features.db` (table: `image_metadata`)
- Extraction → `/photos/vacation/.open-photo-agent/features.db` (tables: `raw_features`, `extracted_features`)

When viewing, the UI queries the root folder's database, finds metadata but not extraction results, or vice versa.

### Double-Save Bug

Additionally, in `SequentialProcessor.process_paths()`, extraction results are saved twice:
1. Inside `process_image()` at line 206
2. In `process_paths()` at line 276

## Solution

### Primary Fix: Use Consistent Database

Modify `SequentialProcessor._save_result()` to use `self._db.save_extraction()` when a folder database is available:

```python
def _save_result(self, result: ProcessingResult) -> None:
    """Save a processing result to sidecar file."""
    if result.image_path:
        data = result.as_dict()
        if self._db is not None:
            # Use the folder's database for consistency with metadata
            self._db.save_extraction(result.image_path, data)
        else:
            # Fallback to sidecar store for backward compatibility
            self._writer.save(result.image_path, data)
```

This ensures:
- Metadata and extraction results go to the same database (root folder)
- Images in subdirectories still reference their full path correctly
- Existing CLI usage without folder parameter still works

### Secondary Fix: Remove Double-Save

In `SequentialProcessor.process_paths()`, remove the redundant `self._save_result(result)` call at line 276, since `process_image()` already saves the result at line 206.

### Connection Leak Fix

In `SequentialProcessor.__init__()`, properly handle the connection returned by `init_db()`:

```python
if folder is not None:
    self._db = FeaturesDatabase(FeaturesDatabase.default_db_path(folder))
    try:
        conn = self._db.init_db()
        conn.close()  # Close the connection after schema initialization
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        self._db = None
```

## Implementation Steps

1. **Fix `_save_result()` method** in `src/sequential_processor.py` to use `self._db.save_extraction()` when available
2. **Remove double-save** in `process_paths()` by removing the redundant `self._save_result(result)` call
3. **Fix connection leak** in `__init__()` by closing the connection after schema initialization
4. **Test** the changes with:
   - CLI processing with subdirectories
   - Web UI processing with subdirectories
   - Verify metadata is visible in detail modal
   - Verify extraction results are saved correctly

## Files to Modify

- `src/sequential_processor.py`
  - `_save_result()` method (around line 371-375)
  - `process_paths()` method (around line 273-281) - remove redundant save
  - `__init__()` method (around line 74-81) - fix connection leak

## Verification

After implementing the fix:
1. Process a folder with images in subdirectories
2. View an image from a subdirectory in the detail modal
3. Verify that both extraction results (description, subjects, etc.) AND metadata (EXIF data) are displayed
4. Query the root folder's database directly to confirm both are stored in the same database

## Expected Outcome

- Metadata and extraction results will be stored in the same database (root folder's `.open-photo-agent/features.db`)
- All data will be retrievable when viewing images from subdirectories
- No data will be lost in separate subdirectory databases
