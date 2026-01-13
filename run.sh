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
fi

# Run application
python3 main.py "$@"
