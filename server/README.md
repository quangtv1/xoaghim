# PP-DocLayout API Server

API Server cho PP-DocLayout_plus-L model (PaddleOCR), chạy trên GPU server để xử lý nhanh hơn.

## Model Info

- **Model**: PP-DocLayout_plus-L
- **Framework**: PaddleOCR / PaddlePaddle
- **Categories**: 20 document element types
- **Accuracy**: 83.2% mAP@0.5

## Yêu cầu hệ thống

- CentOS 7 / Ubuntu 18.04+
- NVIDIA GPU (Tesla V100, RTX, etc.)
- NVIDIA Driver + CUDA 11.8+
- Python 3.8+
- 4GB+ GPU Memory

## Cài đặt thủ công (nếu không dùng setup script)

```bash
# Install PaddlePaddle with CUDA
pip install paddlepaddle-gpu -i https://pypi.tuna.tsinghua.edu.cn/simple

# Install PaddleOCR
pip install paddleocr

# Install other dependencies
pip install fastapi uvicorn pillow numpy opencv-python-headless
```

## Cài đặt nhanh

```bash
# Copy files to server
scp -r server/ root@10.20.0.36:/root/xoaghim/

# SSH to server
ssh root@10.20.0.36

# Run setup
cd /root/xoaghim/server
chmod +x setup_server.sh
./setup_server.sh
```

## Chạy server

### Cách 1: Manual
```bash
source ~/layout_api_venv/bin/activate
cd /root/xoaghim/server
uvicorn layout_api_server:app --host 0.0.0.0 --port 8765
```

### Cách 2: Systemd Service (tự khởi động)
```bash
# Copy service file
cp layout-api.service /etc/systemd/system/

# Enable and start
systemctl daemon-reload
systemctl enable layout-api
systemctl start layout-api

# Check status
systemctl status layout-api
```

## API Endpoints

### Health Check
```bash
curl http://10.20.0.36:8765/health
```

Response:
```json
{
  "status": "ok",
  "cuda_available": true,
  "cuda_device": "Tesla V100-SXM2-32GB",
  "cuda_memory": "32.0 GB"
}
```

### Detect Layout
```bash
# Python example
import base64
import requests

# Encode image
with open("document.png", "rb") as f:
    image_b64 = base64.b64encode(f.read()).decode()

# Send request
response = requests.post(
    "http://10.20.0.36:8765/detect",
    json={
        "image_base64": image_b64,
        "confidence": 0.5,
        "protected_labels": ["plain_text", "table", "title"]
    }
)

print(response.json())
```

Response:
```json
{
  "success": true,
  "regions": [
    {
      "bbox": [100, 200, 500, 400],
      "label": "plain_text",
      "confidence": 0.92
    }
  ]
}
```

## Supported Labels

PP-DocLayout_plus-L detects 20 categories, mapped to internal labels:

| PP-DocLayout Label | Internal Label |
|-------------------|----------------|
| doc_title | title |
| paragraph_title | title |
| text | plain_text |
| abstract | plain_text |
| table | table |
| table_title | table_caption |
| table_note | table_footnote |
| figure | figure |
| figure_title | figure_caption |
| formula | isolate_formula |
| formula_number | formula_caption |
| reference | plain_text |
| footnote | table_footnote |
| header | plain_text |
| footer | plain_text |
| algorithm | plain_text |
| seal | figure |
| chart | figure |
| content | plain_text |
| list | plain_text |

## Firewall

Mở port 8765:
```bash
# CentOS 7
firewall-cmd --permanent --add-port=8765/tcp
firewall-cmd --reload

# hoặc iptables
iptables -A INPUT -p tcp --dport 8765 -j ACCEPT
```

## Cấu hình trong Xóa Vết Ghim

Trong Settings Panel → Bảo vệ văn bản → Server URL:
```
http://10.20.0.36:8765
```

## Performance

| Device | Time per page |
|--------|---------------|
| CPU (i7) | ~2-4s |
| Tesla V100 | ~0.1-0.2s |
| RTX 3080 | ~0.2-0.3s |

## Troubleshooting

### CUDA not available
```bash
# Check NVIDIA driver
nvidia-smi

# Check CUDA
nvcc --version
```

### Port already in use
```bash
# Find process
lsof -i :8765

# Kill process
kill -9 <PID>
```

### Memory issues
```bash
# Clear GPU memory
nvidia-smi --gpu-reset
```
