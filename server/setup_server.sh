#!/bin/bash
# =============================================================================
# Setup Script for PP-DocLayout API Server
# Target: CentOS 7 + NVIDIA Tesla V100
# Model: PP-DocLayout_plus-L (PaddleOCR)
# =============================================================================

set -e

echo "============================================"
echo "PP-DocLayout API Server Setup"
echo "============================================"

# Check if running as root for system packages
if [ "$EUID" -ne 0 ]; then
    echo "Note: Run with sudo for system-wide installation"
fi

# Check NVIDIA GPU
echo ""
echo "[1/5] Checking NVIDIA GPU..."
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo "WARNING: nvidia-smi not found. Make sure NVIDIA drivers are installed."
fi

# Check Python version
echo ""
echo "[2/5] Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo "Found: $PYTHON_VERSION"
else
    echo "ERROR: Python 3 not found. Install with: yum install python3"
    exit 1
fi

# Create virtual environment
echo ""
echo "[3/5] Creating virtual environment..."
VENV_DIR="$HOME/layout_api_venv"
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "Created: $VENV_DIR"
else
    echo "Virtual environment already exists: $VENV_DIR"
fi

# Activate and install dependencies
echo ""
echo "[4/5] Installing dependencies..."
source "$VENV_DIR/bin/activate"

pip install --upgrade pip

# Install PaddlePaddle with CUDA support
echo "Installing PaddlePaddle with CUDA..."
# For CUDA 11.8
pip install paddlepaddle-gpu -i https://pypi.tuna.tsinghua.edu.cn/simple

# Install PaddleOCR
echo "Installing PaddleOCR..."
pip install paddleocr

# Install other dependencies
echo "Installing other packages..."
pip install fastapi uvicorn pillow numpy opencv-python-headless

# Pre-download model
echo ""
echo "[5/5] Pre-downloading PP-DocLayout_plus-L model..."
python3 -c "
from paddleocr import LayoutDetection
print('Downloading PP-DocLayout_plus-L model...')
model = LayoutDetection(model_name='PP-DocLayout_plus-L', use_gpu=False)
print('Model downloaded successfully!')
"

echo ""
echo "============================================"
echo "Setup Complete!"
echo "============================================"
echo ""
echo "To start the server:"
echo "  source $VENV_DIR/bin/activate"
echo "  cd $(dirname "$0")"
echo "  uvicorn layout_api_server:app --host 0.0.0.0 --port 8765"
echo ""
echo "Or use the systemd service (run as root):"
echo "  cp layout-api.service /etc/systemd/system/"
echo "  systemctl daemon-reload"
echo "  systemctl enable layout-api"
echo "  systemctl start layout-api"
echo ""
