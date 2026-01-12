"""
Layout Detector - Document Layout Detection

Chức năng:
- Load model layout detection (lazy loading)
- Detect các vùng layout trong ảnh tài liệu
- Return danh sách ProtectedRegion

Supported models:
- YOLO DocLayNet: Fast and accurate (11 categories) - DEFAULT, RECOMMENDED
- Layout Parser (Detectron2): PubLayNet, HJDataset - legacy
- PP-DocLayout_plus-L (PaddleOCR): High-precision model, 20 categories
- DocLayout-YOLO: Legacy model (deprecated)
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional, Set, Dict
import numpy as np
import os
import subprocess
import sys


def check_text_protection_requirements() -> Dict[str, bool]:
    """
    Check if all required dependencies for text protection are installed.

    Returns:
        Dict with package names and their availability status
    """
    requirements = {
        'shapely': False,
        'layoutparser': False,
    }

    # Check shapely
    try:
        import shapely
        requirements['shapely'] = True
    except ImportError:
        pass

    # Check layoutparser
    try:
        import layoutparser
        requirements['layoutparser'] = True
    except ImportError:
        pass

    # Optional: Check paddleocr (fallback)
    try:
        import paddle
        requirements['paddlepaddle'] = True
    except ImportError:
        pass

    return requirements


def get_missing_requirements() -> List[str]:
    """Get list of missing packages for text protection"""
    reqs = check_text_protection_requirements()
    return [pkg for pkg, installed in reqs.items() if not installed]


def is_text_protection_available() -> bool:
    """Check if all requirements for text protection are met"""
    reqs = check_text_protection_requirements()
    return all(reqs.values())


def install_text_protection_requirements(pip_path: str = None) -> Tuple[bool, str]:
    """
    Install required packages for text protection.

    Args:
        pip_path: Path to pip executable. None = use system pip

    Returns:
        Tuple[success: bool, message: str]
    """
    packages = ['shapely>=2.0.0', 'paddlepaddle>=3.0.0', 'paddleocr>=2.9.0']

    if pip_path is None:
        pip_path = sys.executable
        pip_cmd = [pip_path, '-m', 'pip']
    else:
        pip_cmd = [pip_path]

    try:
        cmd = pip_cmd + ['install'] + packages
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minutes timeout
        )

        if result.returncode == 0:
            return True, "Cài đặt thành công!"
        else:
            return False, f"Lỗi cài đặt:\n{result.stderr}"

    except subprocess.TimeoutExpired:
        return False, "Quá thời gian cài đặt (10 phút)"
    except Exception as e:
        return False, f"Lỗi: {str(e)}"


@dataclass
class ProtectedRegion:
    """Vùng cần bảo vệ không được xóa"""
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    label: str                        # 'plain_text', 'table', ...
    confidence: float                 # 0.0 - 1.0

    def to_shapely(self):
        """Convert sang Shapely Polygon"""
        try:
            from shapely.geometry import box
            return box(self.bbox[0], self.bbox[1],
                       self.bbox[2], self.bbox[3])
        except ImportError:
            return None

    @property
    def width(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def area(self) -> int:
        return self.width * self.height


class PPDocLayoutDetector:
    """
    Wrapper cho PP-DocLayout_plus-L model (PaddleOCR).

    High-precision document layout detection model:
    - 20 categories support
    - 83.2% mAP@0.5
    - Based on RT-DETR-L architecture
    """

    # PP-DocLayout label mapping to our internal labels
    # PP-DocLayout uses different label names than DocLayout-YOLO
    LABEL_MAPPING = {
        'doc_title': 'title',
        'paragraph_title': 'title',
        'text': 'plain_text',
        'abstract': 'plain_text',
        'table': 'table',
        'table_title': 'table_caption',
        'table_note': 'table_footnote',
        'figure': 'figure',
        'figure_title': 'figure_caption',
        'formula': 'isolate_formula',
        'formula_number': 'formula_caption',
        'reference': 'plain_text',
        'footnote': 'table_footnote',
        'header': 'plain_text',
        'footer': 'plain_text',
        'algorithm': 'plain_text',
        'seal': 'figure',
        'chart': 'figure',
        'content': 'plain_text',
        'list': 'plain_text',
        'page_number': 'abandon',
        'image': 'figure',
    }

    # Default labels to protect (using our internal names)
    DEFAULT_PROTECTED_LABELS = {
        'title', 'plain_text', 'table', 'table_caption',
        'table_footnote', 'figure_caption', 'isolate_formula',
        'formula_caption'
    }

    # All labels from PP-DocLayout (internal names after mapping)
    ALL_LABELS = {
        'title', 'plain_text', 'table', 'table_caption',
        'table_footnote', 'figure', 'figure_caption',
        'isolate_formula', 'formula_caption', 'abandon'
    }

    def __init__(self,
                 model_name: str = "PP-DocLayout_plus-L",
                 device: str = 'auto',
                 confidence_threshold: float = 0.5,
                 protected_labels: Optional[Set[str]] = None):
        """
        Initialize PP-DocLayout detector.

        Args:
            model_name: Model name (PP-DocLayout_plus-L, PP-DocLayout-L, etc.)
            device: 'auto', 'cpu', 'gpu'
            confidence_threshold: Confidence threshold (0.0-1.0)
            protected_labels: Set of labels to protect. None = use default
        """
        self.model_name = model_name
        self.model = None
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.protected_labels = protected_labels or self.DEFAULT_PROTECTED_LABELS.copy()
        self._model_loaded = False
        self._load_error = None

    def _load_model(self) -> bool:
        """Lazy load model from PaddleOCR."""
        if self._model_loaded:
            return self.model is not None

        self._model_loaded = True

        try:
            from paddleocr import LayoutDetection
            print(f"[PPDocLayout] Loading model: {self.model_name}")

            # Determine device
            use_gpu = False
            if self.device == 'auto':
                try:
                    import paddle
                    use_gpu = paddle.device.is_compiled_with_cuda()
                except:
                    use_gpu = False
            elif self.device == 'gpu':
                use_gpu = True

            self.model = LayoutDetection(
                model_name=self.model_name,
                use_gpu=use_gpu
            )
            print(f"[PPDocLayout] Model loaded. GPU: {use_gpu}")
            return True

        except ImportError as e:
            self._load_error = f"Missing dependency: {e}"
            print(f"[PPDocLayout] {self._load_error}")
            print("[PPDocLayout] Install: pip install paddlepaddle paddleocr")
            return False
        except Exception as e:
            self._load_error = str(e)
            print(f"[PPDocLayout] Load error: {e}")
            return False

    def is_available(self) -> bool:
        """Check if model is available."""
        if self.model is not None:
            return True
        return self._load_model()

    def get_load_error(self) -> Optional[str]:
        """Get load error message if any."""
        return self._load_error

    def _map_label(self, pp_label: str) -> str:
        """Map PP-DocLayout label to internal label."""
        return self.LABEL_MAPPING.get(pp_label.lower(), pp_label.lower())

    def detect(self,
               image: np.ndarray,
               protected_labels: Optional[Set[str]] = None,
               scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """
        Detect layout regions in image.

        Args:
            image: BGR image (numpy array)
            protected_labels: Override protected labels
            scale_factor: Scale factor for bbox

        Returns:
            List[ProtectedRegion]
        """
        if not self._load_model():
            return []

        if protected_labels is None:
            protected_labels = self.protected_labels

        try:
            import cv2
            # PaddleOCR expects RGB image
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Run detection
            results = self.model.predict(
                rgb_image,
                batch_size=1,
                layout_nms=True
            )

            regions = []
            for result in results:
                # Get detection results
                if hasattr(result, 'boxes') and result.boxes is not None:
                    boxes = result.boxes
                    for i in range(len(boxes)):
                        bbox = boxes[i]
                        x1, y1, x2, y2 = bbox[:4]

                        # Apply scale factor
                        if scale_factor != 1.0:
                            x1 *= scale_factor
                            y1 *= scale_factor
                            x2 *= scale_factor
                            y2 *= scale_factor

                        # Get label and confidence
                        label = result.labels[i] if hasattr(result, 'labels') else 'unknown'
                        conf = result.scores[i] if hasattr(result, 'scores') else 1.0

                        # Filter by confidence
                        if conf < self.confidence_threshold:
                            continue

                        # Map label
                        internal_label = self._map_label(label)

                        # Filter by protected labels
                        if internal_label in protected_labels:
                            regions.append(ProtectedRegion(
                                bbox=(int(x1), int(y1), int(x2), int(y2)),
                                label=internal_label,
                                confidence=float(conf)
                            ))

            return regions

        except Exception as e:
            print(f"[PPDocLayout] Detection error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def detect_all(self,
                   image: np.ndarray,
                   scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """Detect all regions (no label filter)."""
        return self.detect(image, protected_labels=self.ALL_LABELS, scale_factor=scale_factor)

    def set_protected_labels(self, labels: Set[str]):
        """Set labels to protect."""
        self.protected_labels = labels & self.ALL_LABELS

    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold (0.0-1.0)."""
        self.confidence_threshold = max(0.0, min(1.0, threshold))


class DocLayoutYOLO:
    """Wrapper cho DocLayout-YOLO model với lazy loading"""

    # Các label mặc định cần bảo vệ
    DEFAULT_PROTECTED_LABELS = {
        'title', 'plain_text', 'table', 'table_caption',
        'table_footnote', 'figure_caption', 'isolate_formula',
        'formula_caption'
    }

    # Tất cả labels của model
    ALL_LABELS = {
        'title', 'plain_text', 'table', 'table_caption',
        'table_footnote', 'figure', 'figure_caption',
        'isolate_formula', 'formula_caption', 'abandon'
    }

    # HuggingFace model info
    HF_REPO_ID = "juliozhao/DocLayout-YOLO-DocStructBench"
    HF_FILENAME = "doclayout_yolo_docstructbench_imgsz1024.pt"

    def __init__(self,
                 model_path: Optional[str] = None,
                 device: str = 'auto',
                 confidence_threshold: float = 0.5,
                 protected_labels: Optional[Set[str]] = None):
        """
        Khởi tạo DocLayout-YOLO detector.

        Args:
            model_path: Đường dẫn model (.pt). None = auto download
            device: 'auto', 'cpu', 'cuda', 'mps'
            confidence_threshold: Ngưỡng confidence (0.0-1.0)
            protected_labels: Set labels cần bảo vệ. None = dùng mặc định
        """
        self.model = None  # Lazy load
        self.device = device
        self.confidence_threshold = confidence_threshold
        self._model_path = model_path
        self.protected_labels = protected_labels or self.DEFAULT_PROTECTED_LABELS.copy()
        self._model_loaded = False
        self._load_error = None

    def _get_cache_dir(self) -> str:
        """Get model cache directory"""
        cache_dir = os.path.expanduser("~/.cache/xoaghim/doclayout_yolo")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _load_model(self) -> bool:
        """
        Lazy load model từ HuggingFace.
        Returns True nếu load thành công.
        """
        if self._model_loaded:
            return self.model is not None

        self._model_loaded = True

        try:
            # Import dependencies
            try:
                from huggingface_hub import hf_hub_download
                from ultralytics import YOLO
            except ImportError as e:
                self._load_error = f"Missing dependency: {e}"
                print(f"[LayoutDetector] {self._load_error}")
                print("[LayoutDetector] Install: pip install ultralytics huggingface_hub")
                return False

            # Download model if needed
            if self._model_path is None:
                print("[LayoutDetector] Downloading model from HuggingFace...")
                try:
                    self._model_path = hf_hub_download(
                        repo_id=self.HF_REPO_ID,
                        filename=self.HF_FILENAME,
                        cache_dir=self._get_cache_dir()
                    )
                    print(f"[LayoutDetector] Model downloaded: {self._model_path}")
                except Exception as e:
                    self._load_error = f"Download failed: {e}"
                    print(f"[LayoutDetector] {self._load_error}")
                    return False

            # Load model
            print(f"[LayoutDetector] Loading model: {self._model_path}")
            self.model = YOLO(self._model_path)

            # Auto device selection
            if self.device == 'auto':
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.device = 'cuda'
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        self.device = 'mps'
                    else:
                        self.device = 'cpu'
                except ImportError:
                    self.device = 'cpu'

            print(f"[LayoutDetector] Model loaded. Device: {self.device}")
            return True

        except Exception as e:
            self._load_error = str(e)
            print(f"[LayoutDetector] Load error: {e}")
            return False

    def is_available(self) -> bool:
        """Check if model is available (loaded or can be loaded)"""
        if self.model is not None:
            return True
        return self._load_model()

    def get_load_error(self) -> Optional[str]:
        """Get load error message if any"""
        return self._load_error

    def detect(self,
               image: np.ndarray,
               protected_labels: Optional[Set[str]] = None,
               scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """
        Detect layout regions trong image.

        Args:
            image: BGR image (numpy array)
            protected_labels: Override protected labels. None = dùng instance labels
            scale_factor: Tỷ lệ scale bbox (nếu image đã được resize)

        Returns:
            List[ProtectedRegion]: Danh sách vùng cần bảo vệ
        """
        if not self._load_model():
            return []

        if protected_labels is None:
            protected_labels = self.protected_labels

        try:
            # Run inference
            results = self.model.predict(
                image,
                imgsz=1024,
                conf=self.confidence_threshold,
                device=self.device,
                verbose=False
            )

            regions = []
            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    # Get bbox
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    # Apply scale factor
                    if scale_factor != 1.0:
                        x1 *= scale_factor
                        y1 *= scale_factor
                        x2 *= scale_factor
                        y2 *= scale_factor

                    # Get confidence and label
                    conf = box.conf[0].item()
                    cls_id = int(box.cls[0].item())
                    label = self.model.names[cls_id]

                    # Filter by protected labels
                    if label in protected_labels:
                        regions.append(ProtectedRegion(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            label=label,
                            confidence=conf
                        ))

            return regions

        except Exception as e:
            print(f"[LayoutDetector] Detection error: {e}")
            return []

    def detect_all(self,
                   image: np.ndarray,
                   scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """
        Detect tất cả regions (không filter by label).

        Args:
            image: BGR image
            scale_factor: Tỷ lệ scale bbox

        Returns:
            List[ProtectedRegion]: Tất cả regions detected
        """
        return self.detect(image, protected_labels=self.ALL_LABELS, scale_factor=scale_factor)

    def set_protected_labels(self, labels: Set[str]):
        """Set labels cần bảo vệ"""
        self.protected_labels = labels & self.ALL_LABELS

    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold (0.0-1.0)"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))


class RemoteLayoutDetector:
    """
    Remote Layout Detector - Gọi API server từ xa (GPU server).

    Sử dụng khi muốn dùng GPU từ xa thay vì local CPU.
    """

    def __init__(self,
                 api_url: str = "http://10.20.0.36:8765",
                 confidence_threshold: float = 0.5,
                 protected_labels: Optional[Set[str]] = None,
                 timeout: int = 30):
        """
        Khởi tạo Remote Detector.

        Args:
            api_url: URL của API server (vd: http://10.20.0.36:8765)
            confidence_threshold: Ngưỡng confidence
            protected_labels: Set labels cần bảo vệ
            timeout: Timeout cho request (giây)
        """
        self.api_url = api_url.rstrip('/')
        self.confidence_threshold = confidence_threshold
        self.protected_labels = protected_labels or PPDocLayoutDetector.DEFAULT_PROTECTED_LABELS.copy()
        self.timeout = timeout
        self._available = None

    def is_available(self) -> bool:
        """Check if remote server is available"""
        print(f"[DEBUG RemoteDetector] is_available called, api_url={self.api_url}")

        # Chỉ cache kết quả thành công, luôn retry nếu trước đó thất bại
        if self._available is True:
            print("[DEBUG RemoteDetector] Returning cached True")
            return True

        try:
            import urllib.request
            url = f"{self.api_url}/health"
            print(f"[DEBUG RemoteDetector] Checking health: {url}")
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                self._available = response.status == 200
                print(f"[DEBUG RemoteDetector] Health response: {response.status}")
        except Exception as e:
            print(f"[DEBUG RemoteDetector] Health check failed: {e}")
            self._available = False

        print(f"[DEBUG RemoteDetector] is_available = {self._available}")
        return self._available

    def detect(self,
               image: np.ndarray,
               protected_labels: Optional[Set[str]] = None,
               scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """
        Detect layout regions via remote API.

        Args:
            image: BGR image (numpy array)
            protected_labels: Override protected labels
            scale_factor: Scale factor for bbox

        Returns:
            List[ProtectedRegion]
        """
        import json
        import base64
        import urllib.request
        import cv2

        print(f"[DEBUG RemoteDetector] detect called, image shape: {image.shape}")

        if protected_labels is None:
            protected_labels = self.protected_labels

        print(f"[DEBUG RemoteDetector] protected_labels: {protected_labels}")

        try:
            # Encode image to base64 PNG
            _, buffer = cv2.imencode('.png', image)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            print(f"[DEBUG RemoteDetector] Image encoded, size: {len(image_base64)} bytes")

            # Build request
            payload = {
                "image_base64": image_base64,
                "confidence": self.confidence_threshold,
                "protected_labels": list(protected_labels)
            }

            data = json.dumps(payload).encode('utf-8')
            url = f"{self.api_url}/detect"
            print(f"[DEBUG RemoteDetector] Sending request to: {url}")

            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            # Send request
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))

            print(f"[DEBUG RemoteDetector] Response: success={result.get('success')}, regions={len(result.get('regions', []))}")

            if not result.get('success'):
                print(f"[RemoteDetector] Error: {result.get('error')}")
                return []

            # Convert to ProtectedRegion
            regions = []
            for r in result.get('regions', []):
                bbox = r['bbox']
                if scale_factor != 1.0:
                    bbox = [int(x * scale_factor) for x in bbox]
                regions.append(ProtectedRegion(
                    bbox=tuple(bbox),
                    label=r['label'],
                    confidence=r['confidence']
                ))
                print(f"[DEBUG RemoteDetector] Region: {r['label']} @ {bbox}")

            print(f"[DEBUG RemoteDetector] Total regions: {len(regions)}")
            return regions

        except Exception as e:
            print(f"[RemoteDetector] Request error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold"""
        self.confidence_threshold = max(0.0, min(1.0, threshold))

    def set_protected_labels(self, labels: Set[str]):
        """Set protected labels"""
        self.protected_labels = labels


class LayoutParserDetector:
    """
    Wrapper cho Layout Parser (Detectron2-based).

    Sử dụng PubLayNet model để detect document layout.
    Categories: Text, Title, List, Table, Figure
    """

    # PubLayNet label mapping to internal labels
    LABEL_MAPPING = {
        'text': 'plain_text',
        'title': 'title',
        'list': 'plain_text',
        'table': 'table',
        'figure': 'figure',
    }

    # Default labels to protect
    DEFAULT_PROTECTED_LABELS = {
        'title', 'plain_text', 'table', 'figure'
    }

    # All labels from PubLayNet
    ALL_LABELS = {'title', 'plain_text', 'table', 'figure'}

    # Model cache directory
    MODEL_CACHE_DIR = os.path.expanduser("~/.cache/layoutparser/PubLayNet")

    def __init__(self,
                 confidence_threshold: float = 0.5,
                 protected_labels: Optional[Set[str]] = None,
                 device: str = 'auto'):
        """
        Initialize Layout Parser detector.

        Args:
            confidence_threshold: Confidence threshold (0.0-1.0)
            protected_labels: Set of labels to protect. None = use default
            device: 'auto', 'cpu', 'cuda'
        """
        self.model = None
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.protected_labels = protected_labels or self.DEFAULT_PROTECTED_LABELS.copy()
        self._model_loaded = False
        self._load_error = None

    def _ensure_model_downloaded(self) -> Tuple[str, str]:
        """Download model if not exists. Returns (config_path, model_path)."""
        os.makedirs(self.MODEL_CACHE_DIR, exist_ok=True)

        config_path = os.path.join(self.MODEL_CACHE_DIR, "config.yml")
        model_path = os.path.join(self.MODEL_CACHE_DIR, "model_final.pth")

        # Download if not exists
        if not os.path.exists(config_path) or not os.path.exists(model_path):
            print("[LayoutParser] Downloading PubLayNet model...")
            import urllib.request

            # Download config
            if not os.path.exists(config_path):
                urllib.request.urlretrieve(
                    "https://www.dropbox.com/s/f3b12qc4hc0yh4m/config.yml?dl=1",
                    config_path
                )

            # Download model weights
            if not os.path.exists(model_path):
                urllib.request.urlretrieve(
                    "https://www.dropbox.com/s/dgy9c10wykk4lq4/model_final.pth?dl=1",
                    model_path
                )
            print("[LayoutParser] Model downloaded.")

        return config_path, model_path

    def _load_model(self) -> bool:
        """Lazy load model."""
        if self._model_loaded:
            return self.model is not None

        self._model_loaded = True

        try:
            import layoutparser as lp

            # Ensure model is downloaded
            config_path, model_path = self._ensure_model_downloaded()
            print(f"[LayoutParser] Loading model from: {model_path}")

            # Determine device
            device = self.device
            if device == 'auto':
                try:
                    import torch
                    device = 'cuda' if torch.cuda.is_available() else 'cpu'
                except ImportError:
                    device = 'cpu'

            # Load model with local paths
            self.model = lp.Detectron2LayoutModel(
                config_path=config_path,
                model_path=model_path,
                extra_config=["MODEL.ROI_HEADS.SCORE_THRESH_TEST", self.confidence_threshold],
                label_map={0: "text", 1: "title", 2: "list", 3: "table", 4: "figure"}
            )
            print(f"[LayoutParser] Model loaded. Device: {device}")
            return True

        except ImportError as e:
            self._load_error = f"Missing dependency: {e}"
            print(f"[LayoutParser] {self._load_error}")
            print("[LayoutParser] Install: pip install layoutparser 'detectron2@git+https://github.com/facebookresearch/detectron2.git'")
            return False
        except Exception as e:
            self._load_error = str(e)
            print(f"[LayoutParser] Load error: {e}")
            return False

    def is_available(self) -> bool:
        """Check if model is available."""
        if self.model is not None:
            return True
        return self._load_model()

    def get_load_error(self) -> Optional[str]:
        """Get load error message if any."""
        return self._load_error

    def _map_label(self, lp_label: str) -> str:
        """Map Layout Parser label to internal label."""
        return self.LABEL_MAPPING.get(lp_label.lower(), lp_label.lower())

    def detect(self,
               image: np.ndarray,
               protected_labels: Optional[Set[str]] = None,
               scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """
        Detect layout regions in image.

        Args:
            image: BGR image (numpy array)
            protected_labels: Override protected labels
            scale_factor: Scale factor for bbox

        Returns:
            List[ProtectedRegion]
        """
        if not self._load_model():
            return []

        if protected_labels is None:
            protected_labels = self.protected_labels

        try:
            import cv2

            # Layout Parser expects RGB image
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Run detection
            layout = self.model.detect(rgb_image)

            regions = []
            for block in layout:
                # Get bbox
                x1, y1, x2, y2 = block.block.x_1, block.block.y_1, block.block.x_2, block.block.y_2

                # Apply scale factor
                if scale_factor != 1.0:
                    x1 *= scale_factor
                    y1 *= scale_factor
                    x2 *= scale_factor
                    y2 *= scale_factor

                # Get label and confidence
                label = block.type.lower() if hasattr(block, 'type') else 'unknown'
                conf = block.score if hasattr(block, 'score') else 1.0

                # Filter by confidence threshold
                if conf < self.confidence_threshold:
                    continue

                # Map label
                internal_label = self._map_label(label)

                # Filter by protected labels
                if internal_label in protected_labels:
                    regions.append(ProtectedRegion(
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        label=internal_label,
                        confidence=float(conf)
                    ))

            return regions

        except Exception as e:
            print(f"[LayoutParser] Detection error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def detect_all(self,
                   image: np.ndarray,
                   scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """Detect all regions (no label filter)."""
        return self.detect(image, protected_labels=self.ALL_LABELS, scale_factor=scale_factor)

    def set_protected_labels(self, labels: Set[str]):
        """Set labels to protect."""
        self.protected_labels = labels & self.ALL_LABELS

    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold (0.0-1.0)."""
        self.confidence_threshold = max(0.0, min(1.0, threshold))


class YOLODocLayNetDetector:
    """
    YOLO DocLayNet Detector - Fast and accurate document layout detection.

    Model: yolo-doclaynet (trained on DocLayNet dataset)
    Categories (11): Text, Picture, Caption, Section-header, Footnote,
                     Formula, Table, List-item, Page-header, Page-footer, Title
    Source: https://github.com/ppaanngggg/yolo-doclaynet
    """

    # DocLayNet label mapping to internal labels
    LABEL_MAPPING = {
        'text': 'plain_text',
        'title': 'title',
        'section-header': 'title',
        'list-item': 'plain_text',
        'table': 'table',
        'picture': 'figure',
        'caption': 'figure_caption',
        'formula': 'isolate_formula',
        'footnote': 'table_footnote',
        'page-header': 'abandon',
        'page-footer': 'abandon',
    }

    # Default labels to protect
    DEFAULT_PROTECTED_LABELS = {
        'title', 'plain_text', 'table', 'figure',
        'figure_caption', 'isolate_formula', 'table_footnote'
    }

    # All internal labels
    ALL_LABELS = {
        'title', 'plain_text', 'table', 'figure',
        'figure_caption', 'isolate_formula', 'table_footnote', 'abandon'
    }

    # HuggingFace model info
    HF_REPO_ID = "hantian/yolo-doclaynet"
    HF_FILENAME = "yolov8n-doclaynet.pt"  # Nano model for speed

    # Local cache directory
    MODEL_CACHE_DIR = os.path.expanduser("~/.cache/yolo-doclaynet")

    def __init__(self,
                 model_size: str = 'large',
                 confidence_threshold: float = 0.1,
                 protected_labels: Optional[Set[str]] = None,
                 device: str = 'auto',
                 imgsz: int = 1024):
        """
        Initialize YOLO DocLayNet detector.

        Args:
            model_size: 'nano', 'small', 'medium', 'large'
            confidence_threshold: Confidence threshold (0.0-1.0)
            protected_labels: Set of labels to protect. None = use default
            device: 'auto', 'cpu', 'cuda', 'mps'
            imgsz: Input image size for inference (larger = more accurate but slower)
        """
        self.model_size = model_size
        self.model = None
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.protected_labels = protected_labels or self.DEFAULT_PROTECTED_LABELS.copy()
        self.imgsz = imgsz  # Larger image size = better accuracy
        self._model_loaded = False
        self._load_error = None

        # Model filename mapping - YOLOv12 (best accuracy/speed ratio)
        self._model_files = {
            'nano': 'yolov12n-doclaynet.pt',
            'small': 'yolov12s-doclaynet.pt',
            'medium': 'yolov12m-doclaynet.pt',
            'large': 'yolov12l-doclaynet.pt',
        }

    def _get_model_path(self) -> str:
        """Get or download model file."""
        os.makedirs(self.MODEL_CACHE_DIR, exist_ok=True)

        filename = self._model_files.get(self.model_size, 'yolov8n-doclaynet.pt')
        local_path = os.path.join(self.MODEL_CACHE_DIR, filename)

        # Download if not exists
        if not os.path.exists(local_path):
            print(f"[YOLODocLayNet] Downloading {filename} from HuggingFace...")
            try:
                from huggingface_hub import hf_hub_download
                local_path = hf_hub_download(
                    repo_id=self.HF_REPO_ID,
                    filename=filename,
                    local_dir=self.MODEL_CACHE_DIR
                )
                print(f"[YOLODocLayNet] Model downloaded: {local_path}")
            except Exception as e:
                print(f"[YOLODocLayNet] Download error: {e}")
                raise

        return local_path

    def _load_model(self) -> bool:
        """Lazy load YOLO model."""
        if self._model_loaded:
            return self.model is not None

        self._model_loaded = True

        try:
            from ultralytics import YOLO

            # Get model path (download if needed)
            model_path = self._get_model_path()
            print(f"[YOLODocLayNet] Loading model: {model_path}")

            # Load model
            self.model = YOLO(model_path)

            # Auto device selection
            if self.device == 'auto':
                try:
                    import torch
                    if torch.cuda.is_available():
                        self.device = 'cuda'
                    elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                        self.device = 'mps'
                    else:
                        self.device = 'cpu'
                except ImportError:
                    self.device = 'cpu'

            print(f"[YOLODocLayNet] Model loaded. Size: {self.model_size}, Device: {self.device}, ImgSz: {self.imgsz}")
            return True

        except ImportError as e:
            self._load_error = f"Missing dependency: {e}"
            print(f"[YOLODocLayNet] {self._load_error}")
            print("[YOLODocLayNet] Install: pip install ultralytics huggingface_hub")
            return False
        except Exception as e:
            self._load_error = str(e)
            print(f"[YOLODocLayNet] Load error: {e}")
            return False

    def is_available(self) -> bool:
        """Check if model is available."""
        if self.model is not None:
            return True
        return self._load_model()

    def get_load_error(self) -> Optional[str]:
        """Get load error message if any."""
        return self._load_error

    def _map_label(self, yolo_label: str) -> str:
        """Map YOLO DocLayNet label to internal label."""
        return self.LABEL_MAPPING.get(yolo_label.lower(), yolo_label.lower())

    def detect(self,
               image: np.ndarray,
               protected_labels: Optional[Set[str]] = None,
               scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """
        Detect layout regions in image.

        Args:
            image: BGR image (numpy array)
            protected_labels: Override protected labels
            scale_factor: Scale factor for bbox

        Returns:
            List[ProtectedRegion]
        """
        if not self._load_model():
            return []

        if protected_labels is None:
            protected_labels = self.protected_labels

        try:
            # Run inference with larger image size for better accuracy
            results = self.model.predict(
                image,
                imgsz=self.imgsz,
                conf=self.confidence_threshold,
                device=self.device,
                verbose=False
            )

            regions = []
            for result in results:
                if result.boxes is None:
                    continue

                for box in result.boxes:
                    # Get bbox
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    # Apply scale factor
                    if scale_factor != 1.0:
                        x1 *= scale_factor
                        y1 *= scale_factor
                        x2 *= scale_factor
                        y2 *= scale_factor

                    # Get confidence and label
                    conf = box.conf[0].item()
                    cls_id = int(box.cls[0].item())
                    label = self.model.names[cls_id]

                    # Filter by confidence
                    if conf < self.confidence_threshold:
                        continue

                    # Map label
                    internal_label = self._map_label(label)

                    # Filter by protected labels
                    if internal_label in protected_labels:
                        regions.append(ProtectedRegion(
                            bbox=(int(x1), int(y1), int(x2), int(y2)),
                            label=internal_label,
                            confidence=float(conf)
                        ))

            return regions

        except Exception as e:
            print(f"[YOLODocLayNet] Detection error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def detect_all(self,
                   image: np.ndarray,
                   scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """Detect all regions (no label filter)."""
        return self.detect(image, protected_labels=self.ALL_LABELS, scale_factor=scale_factor)

    def set_protected_labels(self, labels: Set[str]):
        """Set labels to protect."""
        self.protected_labels = labels & self.ALL_LABELS

    def set_confidence_threshold(self, threshold: float):
        """Set confidence threshold (0.0-1.0)."""
        self.confidence_threshold = max(0.0, min(1.0, threshold))


# Singleton instance for shared use
_yolo_doclaynet_instance: Optional[YOLODocLayNetDetector] = None
_detector_instance: Optional[LayoutParserDetector] = None
_paddle_detector_instance: Optional[PPDocLayoutDetector] = None
_legacy_detector_instance: Optional[DocLayoutYOLO] = None
_remote_detector_instance: Optional[RemoteLayoutDetector] = None


def get_layout_detector() -> YOLODocLayNetDetector:
    """Get shared YOLODocLayNetDetector instance - NEW DEFAULT detector"""
    return get_yolo_doclaynet_detector()


def get_layoutparser_detector() -> LayoutParserDetector:
    """Get shared LayoutParserDetector instance (legacy, replaced by YOLO DocLayNet)"""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = LayoutParserDetector()
    return _detector_instance


def get_paddle_detector() -> PPDocLayoutDetector:
    """Get shared PPDocLayoutDetector instance (PaddleOCR)"""
    global _paddle_detector_instance
    if _paddle_detector_instance is None:
        _paddle_detector_instance = PPDocLayoutDetector()
    return _paddle_detector_instance


def get_legacy_detector() -> DocLayoutYOLO:
    """Get shared DocLayoutYOLO instance (legacy, deprecated)"""
    global _legacy_detector_instance
    if _legacy_detector_instance is None:
        _legacy_detector_instance = DocLayoutYOLO()
    return _legacy_detector_instance


def get_remote_detector(api_url: str = "http://10.20.0.36:8765") -> RemoteLayoutDetector:
    """Get shared RemoteLayoutDetector instance"""
    global _remote_detector_instance
    if _remote_detector_instance is None or _remote_detector_instance.api_url != api_url:
        _remote_detector_instance = RemoteLayoutDetector(api_url=api_url)
    return _remote_detector_instance


def get_yolo_doclaynet_detector() -> YOLODocLayNetDetector:
    """Get shared YOLODocLayNetDetector instance - NEW DEFAULT detector"""
    global _yolo_doclaynet_instance
    if _yolo_doclaynet_instance is None:
        _yolo_doclaynet_instance = YOLODocLayNetDetector()
    return _yolo_doclaynet_instance


def detect_layout(image: np.ndarray,
                  confidence: float = 0.1,
                  protected_labels: Optional[Set[str]] = None) -> List[ProtectedRegion]:
    """
    Convenience function để detect layout using YOLO DocLayNet.

    Args:
        image: BGR image
        confidence: Confidence threshold
        protected_labels: Labels cần bảo vệ

    Returns:
        List[ProtectedRegion]
    """
    detector = get_layout_detector()
    detector.set_confidence_threshold(confidence)
    return detector.detect(image, protected_labels)
