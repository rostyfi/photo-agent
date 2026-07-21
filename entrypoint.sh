#!/bin/bash
set -e

# Export LD_LIBRARY_PATH to ensure it's available to all child processes
export LD_LIBRARY_PATH=/usr/local/lib:/usr/lib/x86_64-linux-gnu:/usr/lib:${LD_LIBRARY_PATH}

echo "=== Environment ==="
echo "LD_LIBRARY_PATH: $LD_LIBRARY_PATH"
echo "PYTHONPATH: $PYTHONPATH"
echo ""

# Check if vec0.so is in LD_LIBRARY_PATH directories
echo "=== Checking for vec0.so in LD_LIBRARY_PATH ==="
for dir in $(echo $LD_LIBRARY_PATH | tr ':' ' '); do
    if [ -f "$dir/vec0.so" ]; then
        echo "✓ Found vec0.so in: $dir"
    fi
done
echo ""

# Verify custom SQLite has extension loading
python3 -c "import sqlite3; conn = sqlite3.connect(':memory:'); conn.enable_load_extension(True); print('✓ SQLite extension loading ENABLED')" 2>&1

# Verify sqlite-vec and vec0.so
python3 -c "
import sqlite_vec
import os
p = os.path.join(os.path.dirname(sqlite_vec.__file__), 'vec0.so')
print('✓ sqlite_vec package location:', os.path.dirname(sqlite_vec.__file__))
print('✓ vec0.so path:', p)
print('✓ vec0.so exists:', os.path.exists(p))
if os.path.exists(p):
    print('✓ vec0.so size:', os.path.getsize(p), 'bytes')
    # Try to load it
    import sqlite3
    conn = sqlite3.connect(':memory:')
    conn.enable_load_extension(True)
    
    try:
        conn.load_extension(p)
        print('✓ vec0.so LOADED SUCCESSFULLY')
    except Exception as e:
        print('✗ Failed to load vec0.so:', e)
        # Check dependencies
        import subprocess
        result = subprocess.run(['ldd', p], capture_output=True, text=True)
        print('vec0.so dependencies:')
        print(result.stdout)
        if result.stderr:
            print('ldd stderr:', result.stderr)
" 2>&1

# Run the app using the system sqlite3 with extension support
exec python3 << 'EOF'

# Import and run the app
from app import create_app
import signal
from src.state import request_shutdown

app, config = create_app()
DASH_HOST = config.dash_host
DASH_PORT = config.dash_port
DASH_DEBUG = config.dash_debug

signal.signal(signal.SIGINT, lambda _sig, _frame: request_shutdown())
signal.signal(signal.SIGTERM, lambda _sig, _frame: request_shutdown())
print(f"Starting Photo Feature Extractor web app on http://{DASH_HOST}:{DASH_PORT}")
app.run(host=DASH_HOST, port=DASH_PORT, debug=DASH_DEBUG)
EOF
