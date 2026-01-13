"""
Layout Detection API Server
Chạy trên server có GPU

Model: Layout Parser (Detectron2) - PubLayNet
- 5 categories: Text, Title, List, Table, Figure
- Faster R-CNN R50 FPN

Cách cài đặt trên server:
    pip install layoutparser torchvision
    pip install "detectron2@git+https://github.com/facebookresearch/detectron2.git@v0.5#egg=detectron2"
    pip install fastapi uvicorn pillow

Cách chạy:
    uvicorn layout_api_server:app --host 0.0.0.0 --port 8765
"""

import io
import base64
from typing import List, Optional

import numpy as np
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Lazy load model
_model = None

# PubLayNet label mapping to internal labels
LABEL_MAPPING = {
    'text': 'plain_text',
    'title': 'title',
    'list': 'plain_text',
    'table': 'table',
    'figure': 'figure',
}


def get_model():
    """Lazy load Layout Parser model"""
    global _model

    if _model is None:
        print("[Server] Loading Layout Parser (PubLayNet) model...")
        import layoutparser as lp

        _model = lp.Detectron2LayoutModel(
            'lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config',
            extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", 0.5],
            label_map={0: "text", 1: "title", 2: "list", 3: "table", 4: "figure"}
        )
        print("[Server] Layout Parser model loaded.")

    return _model


def map_label(lp_label: str) -> str:
    """Map Layout Parser label to internal label"""
    return LABEL_MAPPING.get(lp_label.lower(), lp_label.lower())


# FastAPI app
app = FastAPI(
    title="Layout Parser API",
    description="API for document layout detection using Layout Parser (Detectron2)",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DetectRequest(BaseModel):
    image_base64: str
    confidence: float = 0.5
    protected_labels: Optional[List[str]] = None


class Region(BaseModel):
    bbox: List[int]
    label: str
    confidence: float


class DetectResponse(BaseModel):
    success: bool
    regions: List[Region]
    error: Optional[str] = None


@app.get("/")
async def root():
    return {"status": "ok", "service": "Layout Parser API"}


@app.get("/health")
async def health():
    try:
        import torch
        gpu_available = torch.cuda.is_available()
        gpu_name = torch.cuda.get_device_name(0) if gpu_available else None
        gpu_memory = f"{torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB" if gpu_available else None

        return {
            "status": "ok",
            "cuda_available": gpu_available,
            "cuda_device": gpu_name,
            "cuda_memory": gpu_memory
        }
    except Exception as e:
        return {"status": "ok", "cuda_available": False, "error": str(e)}


@app.post("/detect", response_model=DetectResponse)
async def detect_layout(request: DetectRequest):
    try:
        # Decode image
        image_data = base64.b64decode(request.image_base64)
        image = Image.open(io.BytesIO(image_data))

        # Convert to numpy RGB
        img_np = np.array(image)
        if len(img_np.shape) == 2:
            img_np = np.stack([img_np] * 3, axis=-1)
        elif img_np.shape[2] == 4:
            img_np = img_np[:, :, :3]

        # Get model
        model = get_model()

        # Default protected labels
        default_labels = {
            'title', 'plain_text', 'table', 'figure'
        }
        protected_labels = set(request.protected_labels) if request.protected_labels else default_labels

        # Run inference
        layout = model.detect(img_np)

        # Extract regions
        regions = []
        for block in layout:
            # Get bbox
            x1, y1, x2, y2 = block.block.x_1, block.block.y_1, block.block.x_2, block.block.y_2

            # Get label and confidence
            raw_label = block.type.lower() if hasattr(block, 'type') else 'unknown'
            conf = block.score if hasattr(block, 'score') else 1.0

            # Filter by confidence
            if conf < request.confidence:
                continue

            # Map label
            label = map_label(raw_label)

            if label in protected_labels:
                regions.append(Region(
                    bbox=[int(x1), int(y1), int(x2), int(y2)],
                    label=label,
                    confidence=float(conf)
                ))

        return DetectResponse(success=True, regions=regions)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return DetectResponse(success=False, regions=[], error=str(e))


@app.post("/detect_batch")
async def detect_batch(requests: List[DetectRequest]):
    results = []
    for req in requests:
        result = await detect_layout(req)
        results.append(result)
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
