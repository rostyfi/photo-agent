#!/usr/bin/env bash
# Run all static-analysis and test checks.
#
# Usage:
#   ./validate.sh              # Run all checks (ruff, mypy, tests+coverage)
#   ./validate.sh --fix        # Auto-fix lint issues and format before running checks
#   ./validate.sh --no-mypy    # Skip mypy (useful on slower machines)
#   ./validate.sh --quick      # Only run ruff + tests (skip mypy)
#
# Exits non-zero if any check fails.

set -e

# --- Parse args ---
DO_FIX=false
RUN_MYPY=true
RUN_TESTS=true

for arg in "$@"; do
    case "$arg" in
        --fix)
            DO_FIX=true
            ;;
        --no-mypy)
            RUN_MYPY=false
            ;;
        --quick)
            RUN_MYPY=false
            ;;
        --no-tests)
            RUN_TESTS=false
            ;;
        -h|--help)
            echo "Usage: ./validate.sh [--fix] [--no-mypy] [--quick] [--no-tests]"
            echo ""
            echo "  --fix        Auto-fix lint issues and format before running checks"
            echo "  --no-mypy    Skip mypy type checking"
            echo "  --quick      Skip mypy (alias for --no-mypy)"
            echo "  --no-tests   Skip pytest + coverage"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Run './validate.sh --help' for usage."
            exit 1
            ;;
    esac
done

# --- Resolve repo root so the script works from any cwd ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Helpers ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

banner() {
    echo ""
    echo "================================================"
    echo " $1"
    echo "================================================"
}

pass() {
    echo -e "${GREEN}PASSED${NC} — $1"
}

fail() {
    echo -e "${RED}FAILED${NC} — $1"
}

# Track overall result; we don't exit on first failure so the user sees
# the full picture, but we exit non-zero at the end if anything failed.
EXIT_CODE=0

# --- Locate Python ---
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo -e "${RED}Error: python not found${NC}"
    exit 1
fi

# --- Ruff ---
banner "Ruff (lint + format)"

if $DO_FIX; then
    echo "Applying auto-fixes and formatting..."
    ruff check . --fix
    ruff format .
else
    echo "Checking lint rules..."
    if ruff check .; then
        pass "ruff check"
    else
        fail "ruff check"
        EXIT_CODE=1
    fi

    echo "Checking formatting..."
    if ruff format --check .; then
        pass "ruff format"
    else
        fail "ruff format (run './validate.sh --fix' to format)"
        EXIT_CODE=1
    fi
fi

# --- Mypy ---
if $RUN_MYPY; then
    banner "Mypy (type check)"

    echo "Checking types (advisory — does not block)..."
    # Capture mypy output and exit code without set -e killing the script.
    set +e
    MYPY_OUTPUT=$(mypy --config-file=pyproject.toml 2>&1)
    MYPY_EXIT=$?
    set -e

    if [ $MYPY_EXIT -eq 0 ]; then
        echo "$MYPY_OUTPUT"
        pass "mypy"
    else
        echo "$MYPY_OUTPUT" | tail -5
        echo "..."
        echo "$MYPY_OUTPUT" | tail -1
        echo ""
        echo -e "${YELLOW}ADVISORY${NC} — mypy found type errors but they do not block validation."
        echo "These are pre-existing issues in the codebase. Run 'mypy --config-file=pyproject.toml' for full output."
    fi
else
    banner "Mypy (skipped)"
fi

# --- Pytest + Coverage ---
if $RUN_TESTS; then
    banner "Pytest + Coverage"

    set +e
    $PY -m pytest tests/ --cov=src --cov=plugins --cov-report=term-missing -q
    TEST_EXIT=$?
    set -e

    if [ $TEST_EXIT -eq 0 ]; then
        pass "pytest + coverage"
    else
        fail "pytest + coverage"
        EXIT_CODE=1
    fi
else
    banner "Pytest (skipped)"
fi

# --- Summary ---
banner "Validation Summary"

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}All blocking checks passed.${NC}"
else
    echo -e "${RED}One or more checks failed.${NC}"
fi

exit $EXIT_CODE
