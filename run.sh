#!/bin/bash
# Xóa Vết Ghim PDF - Run script

# Change to script directory
cd "$(dirname "$0")"

# Fix Qt plugin path for Linux (Rocky/RHEL/CentOS)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PYQT5_PATH=$(python3 -c "import PyQt5; print(PyQt5.__path__[0])" 2>/dev/null)
    if [ -n "$PYQT5_PATH" ] && [ -d "$PYQT5_PATH/Qt5/lib" ]; then
        export LD_LIBRARY_PATH="$PYQT5_PATH/Qt5/lib:$LD_LIBRARY_PATH"
        export QT_PLUGIN_PATH="$PYQT5_PATH/Qt5/plugins"
        echo "[run.sh] Using PyQt5 Qt libs from: $PYQT5_PATH/Qt5/lib"
    fi

    # Check GPU availability
    if command -v nvidia-smi &> /dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        if [ -n "$GPU_NAME" ]; then
            echo "[run.sh] GPU detected: $GPU_NAME"
        fi
    fi
fi

# Run application
# Use homebrew python if available, otherwise system python
if [ -x "/opt/homebrew/bin/python3.10" ]; then
    /opt/homebrew/bin/python3.10 main.py "$@"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    /opt/homebrew/bin/python3 main.py "$@"
elif [ -x "/usr/local/bin/python3" ]; then
    /usr/local/bin/python3 main.py "$@"
else
    python3 main.py "$@"
fi
