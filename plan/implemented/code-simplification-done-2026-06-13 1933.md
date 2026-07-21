# Code Simplification Plan

> **Status:** In Progress  
> **Created:** 2026-06-13 16:53:46  
> **Last Updated:** 2026-06-13  
> **Owner:** @rost  

## Overview

This plan addresses technical debt and code duplication that has accumulated in the Open Photo Agent codebase. The project has grown from a simple CLI tool to a full-featured web application with vector embeddings, batch processing, WAL crash recovery, and multiple UI components. This growth has introduced significant redundancy, particularly around embedding generation, error handling, and configuration management.

**Current state:**
- ~3,148 Python files across the project
- ~9,177 lines in `src/` directory alone
- 46 occurrences of the string `"sqlite-vss is a HARD REQUIREMENT"` (clear duplication indicator)
- Duplicate embedding logic in multiple strategy classes
- Complex callback system with 15+ separate files
- Mixed error handling patterns

## Motivation

### Why are we building this?

1. **Maintainability**: Reduce code duplication to make the codebase easier to understand, modify, and extend
2. **Reliability**: Consistent error handling reduces bugs and improves user experience
3. **Performance**: Eliminate redundant operations (e.g., repeated health checks, duplicate DB connections)
4. **Developer Experience**: Cleaner code attracts contributors and reduces onboarding time
5. **Future Growth**: A cleaner architecture makes it easier to add new features (e.g., additional LLM backends, new embedding models)

### What problem does it solve?

- **Code duplication** makes changes error-prone (must update multiple places)
- **Inconsistent patterns** create confusion and potential bugs
- **Excessive complexity** in callbacks and coordinators makes debugging difficult
- **Poor separation of concerns** leads to tightly coupled components

## Requirements

### Concrete requirements - What must this feature do?

#### 1. **Centralize Embedding Logic** (P0 - High Priority)
- [ ] Create a single `EmbeddingService` class that encapsulates all embedding generation, storage, and error handling
- [ ] Eliminate duplicate embedding code in `SequentialStrategy` and `WALSequentialStrategy`
- [ ] Standardize error messages (especially the repeated "sqlite-vss is a HARD REQUIREMENT" string)
- [ ] Provide a single, consistent interface for embedding operations across CLI and web UI

#### 2. **Create Common Error Constants** (P0 - High Priority)
- [ ] Define a central location for all repeated error messages
- [ ] Replace 46+ occurrences of "sqlite-vss is a HARD REQUIREMENT" with a constant
- [ ] Standardize embedding-related error messages
- [ ] Ensure all error messages are consistent and user-friendly

#### 3. **Simplify Configuration Management** (P1 - Medium Priority)
- [ ] Reduce duplication between `AppConfig` and `ProcessingConfig`
- [ ] Create a single source of truth for configuration defaults
- [ ] Simplify the flow of configuration from env vars → app → coordinators → processors

#### 4. **Consolidate Database Operations** (P1 - Medium Priority)
- [ ] Reduce duplicate DB connection and initialization code
- [ ] Create context managers or utilities for common DB operations
- [ ] Standardize how `FeaturesDatabase` is instantiated and used

#### 5. **Streamline Callback Registration** (P2 - Medium Priority)
- [ ] Reduce boilerplate in callback registration
- [ ] Consider using decorators or a registry pattern for callbacks
- [ ] Improve organization of the 15+ callback files

#### 6. **Clean Up CLI (`main.py`)** (P2 - Medium Priority)
- [ ] Extract common logic into reusable functions
- [ ] Reduce code duplication between CLI and web UI processing paths
- [ ] Improve error handling consistency

#### 7. **Improve Logging** (P2 - Medium Priority)
- [ ] Standardize logging patterns across the codebase
- [ ] Reduce verbose/debug logging in production
- [ ] Add more contextual information to error logs

## Design / Approach

### High-level design decisions

#### 1. EmbeddingService Class
```python
# New file: src/services/embedding.py

class EmbeddingService:
    """Centralized service for all embedding operations."""
    
    def __init__(self, config: ProcessingConfig):
        self.config = config
        self._generator = None
        self._db_path = None
    
    def initialize(self, folder: str):
        """Initialize the service with a folder context."""
        self._db_path = FeaturesDatabase.default_db_path(folder)
        self._generator = create_generator(...)
    
    def generate_and_save(self, image_path: str, description: str) -> tuple[list|None, str|None]:
        """Generate embedding from text description and save to DB.
        
        Returns:
            (embedding_vector, error_message) tuple
        """
        # Single source of truth for all embedding logic
        # Handles health checks, generation, saving, error handling
        
    def get_error_message(self, error_type: str) -> str:
        """Get standardized error message."""
        # Centralizes all error messages
```

#### 2. Error Constants Module
```python
# New file: src/constants.py

# Embedding errors
EMBEDDING_VSS_REQUIRED = "sqlite-vss is a HARD REQUIREMENT for vector search."
EMBEDDING_BACKEND_UNAVAILABLE = "Embedding backend is unavailable. " + EMBEDDING_VSS_REQUIRED
EMBEDDING_GENERATION_FAILED = "Embedding generation failed. " + EMBEDDING_VSS_REQUIRED
EMBEDDING_SAVE_FAILED = "Failed to save embedding. " + EMBEDDING_VSS_REQUIRED

# Health check errors
HEALTH_CHECK_FAILED = "Health check failed. Please verify the LLM server is running."
```

#### 3. Configuration Hierarchy
```
AppConfig (from env)
    ↓
ProcessingConfig (snapshot for a processing run)
    ↓
RuntimeConfig (per-request/per-batch overrides)
```

### Data flow

**Current:**
```
CLI/Web UI → BatchCoordinator → Strategy → Processor → Embedding Generation + DB Save
                          ↓
                    (duplicated in each strategy)
```

**Proposed:**
```
CLI/Web UI → BatchCoordinator → Strategy → Processor → EmbeddingService
                                                   ↓
                                         (single implementation)
```

### Architecture choices

1. **Service Pattern**: Use a service class (`EmbeddingService`) to encapsulate cross-cutting concerns
2. **Constants Module**: Centralize all repeated strings in `src/constants.py`
3. **Context Managers**: Use context managers for DB connections to ensure proper cleanup
4. **Dependency Injection**: Pass services (like `EmbeddingService`) to components that need them
5. **Gradual Migration**: Refactor incrementally, maintaining backward compatibility

## Files to modify

### New files to create
```
src/constants.py                    # Centralized error messages and constants
src/services/                      # New services package
├── __init__.py
├── embedding.py                   # EmbeddingService class
└── database.py                   # Database service utilities
```

### Existing files to modify

```
# Core simplification targets
src/coordinator/strategy.py         # Remove duplicate embedding logic (HIGH)
src/coordinator/processor.py       # Simplify embedding integration (HIGH)
src/coordinator/coordinator.py     # Use EmbeddingService (HIGH)
main.py                            # Extract common logic, use constants (MEDIUM)
app.py                             # Use constants (MEDIUM)

# Database-related
src/sidecar/database/db.py         # Add context manager utilities (MEDIUM)

# Callbacks (organize better)
src/callbacks/common.py            # Use constants, reduce duplication (MEDIUM)
src/callbacks/batch.py             # Use EmbeddingService (MEDIUM)
src/callbacks/*.py                 # Standardize error handling (LOW)

# Embedding modules
src/embeddings/ollama.py           # Use constants for error messages (HIGH)
plugins/llm/*.py                   # Use constants (LOW)
```

### Files to review (may need changes)
```
src/config.py                      # Review for simplification opportunities
src/wal.py                          # Review error handling
src/batch_state.py                  # Review for consistency
```

## Implementation Steps

### Phase 1: Foundation (P0 - Can start immediately)
1. **Create `src/constants.py`** with all repeated error messages
   - Identify all 46+ occurrences of "sqlite-vss is a HARD REQUIREMENT"
   - Group related constants (embedding, health check, DB, etc.)
   - Add deprecation warnings for old patterns

2. **Update all files** to use the new constants
   - Start with high-impact files: `strategy.py`, `db.py`, `ollama.py`
   - Use search-and-replace with verification
   - Ensure no functionality changes

3. **Create `src/services/embedding.py`** with `EmbeddingService`
   - Extract embedding generation logic from `SequentialStrategy`
   - Extract embedding saving logic from both strategy classes
   - Handle all error cases consistently
   - Add comprehensive logging

4. **Update `SequentialStrategy`** to use `EmbeddingService`
   - Replace duplicate embedding code with service calls
   - Ensure all existing functionality is preserved
   - Add tests for the refactored code

### Phase 2: Core Refactoring (P0 - After Phase 1)
5. **Update `WALSequentialStrategy`** to use `EmbeddingService`
   - Remove duplicate embedding logic
   - Ensure WAL-specific behavior is preserved

6. **Update `ImageProcessor`** to accept and use `EmbeddingService`
   - Simplify the processor's embedding integration
   - Remove duplicate health check logic

7. **Update `BatchCoordinator`** to create and pass `EmbeddingService`
   - Centralize service creation
   - Pass service to strategies and processors

### Phase 3: Configuration & Callbacks (P1)
8. **Review and simplify configuration**
   - Identify duplication between `AppConfig` and `ProcessingConfig`
   - Consider merging or better separating concerns
   - Simplify config flow through the application

9. **Create database service utilities**
   - Add context managers for DB connections
   - Standardize DB initialization patterns
   - Reduce duplicate connection code

10. **Update callbacks** to use new constants and services
    - Start with `common.py` and `batch.py`
    - Standardize error handling patterns
    - Reduce code duplication

### Phase 4: CLI & Final Cleanup (P2)
11. **Refactor `main.py`**
    - Extract common processing logic
    - Use new constants and services
    - Reduce duplicate code with web UI

12. **Review and clean up logging**
    - Standardize logging patterns
    - Add contextual information
    - Reduce verbose logging

13. **Final review and testing**
    - Run full test suite
    - Manual smoke testing
    - Performance verification

## Testing Plan

### How will this be tested?

#### Unit Tests
- [ ] Add unit tests for `EmbeddingService`
- [ ] Add unit tests for constants (ensure they're being used correctly)
- [ ] Update existing tests to use new patterns
- [ ] Verify backward compatibility

#### Integration Tests
- [ ] Run existing test suite: `python -m pytest tests/`
- [ ] Test CLI: `python main.py <test-image>`
- [ ] Test CLI folder processing: `python main.py <folder>`
- [ ] Test CLI with embeddings: `python main.py <folder> --embedding-model nomic-embed-text`
- [ ] Test CLI find-similar: `python main.py <image> --find-similar`
- [ ] Test web UI: `python app.py` and verify processing

#### Manual Smoke Tests
- [ ] Process a folder with images (CLI)
- [ ] Process a folder with images (Web UI)
- [ ] Verify embeddings are generated and saved
- [ ] Verify find-similar works
- [ ] Test with sqlite-vss not installed (verify graceful error messages)
- [ ] Test with Ollama server down (verify graceful error messages)

#### Performance Tests
- [ ] Verify no performance regression in batch processing
- [ ] Verify memory usage is stable
- [ ] Verify DB operations are efficient

## Edge Cases & Risks

### Things that could go wrong

1. **Breaking Changes**: Refactoring might inadvertently change behavior
   - *Mitigation*: Comprehensive test coverage, incremental changes

2. **Import Order Issues**: Circular imports with new service classes
   - *Mitigation*: Careful dependency management, lazy imports where needed

3. **Performance Regression**: Adding service layer might add overhead
   - *Mitigation*: Measure before and after, optimize if needed

4. **Configuration Conflicts**: Changes to config might break existing deployments
   - *Mitigation*: Maintain backward compatibility, document changes

5. **Embedding Service Failures**: Centralizing embedding logic creates a single point of failure
   - *Mitigation*: Comprehensive error handling, graceful degradation

6. **Test Suite Failures**: Existing tests might fail with refactored code
   - *Mitigation*: Update tests incrementally, verify each change

### Edge cases to handle

1. **Embedding disabled**: Service should handle disabled state gracefully
2. **sqlite-vss not available**: Service should provide clear error messages
3. **Ollama server down**: Service should handle connection failures
4. **Invalid image paths**: Service should validate inputs
5. **DB connection failures**: Service should retry or fail gracefully
6. **Concurrent access**: Service should be thread-safe or document thread-safety

## Success Criteria

- [ ] All 46+ occurrences of "sqlite-vss is a HARD REQUIREMENT" replaced with constants
- [ ] Duplicate embedding logic eliminated from strategy classes
- [ ] All existing tests pass
- [ ] CLI and web UI functionality preserved
- [ ] Code lines reduced by at least 15-20%
- [ ] No performance regression
- [ ] Improved developer feedback on code quality

## References

- [AGENTS.md](../AGENTS.md) - Project architecture and coding standards
- [README.md](../README.md) - Project overview and usage
- [Dockerfile](../Dockerfile) - Deployment configuration
- [requirements.txt](../requirements.txt) - Python dependencies

## Appendix: Current Duplication Analysis

### Embedding Logic Duplication
Both `SequentialStrategy` and `WALSequentialStrategy` contain nearly identical code:
- Health check before embedding generation
- Description extraction from parsed results
- Text-based embedding generation (not image-based)
- Embedding save to database
- Error handling with "sqlite-vss is a HARD REQUIREMENT" messages

**Lines of duplicate code:** ~100+ lines across both files

### Error Message Duplication
- `"sqlite-vss is a HARD REQUIREMENT"`: 46 occurrences
- Similar embedding-related error patterns: 20+ occurrences
- Health check error messages: 10+ occurrences

### Configuration Duplication
- `AppConfig` and `ProcessingConfig` have overlapping fields
- Embedding configuration scattered across multiple places
- Default values defined in multiple locations

## Next Steps

1. **Review this plan** - Get feedback from team members
2. **Prioritize** - Confirm P0/P1/P2 priorities
3. **Start with Phase 1** - Create constants.py and EmbeddingService
4. **Iterate** - Refine based on feedback and learnings
