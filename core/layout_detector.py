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
        # Chỉ cache kết quả thành công, luôn retry nếu trước đó thất bại
        if self._available is True:
            return True

        try:
            import urllib.request
            url = f"{self.api_url}/health"
            req = urllib.request.Request(url, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                self._available = response.status == 200
        except Exception:
            self._available = False

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

        if protected_labels is None:
            protected_labels = self.protected_labels

        try:
            # Encode image to base64 PNG
            _, buffer = cv2.imencode('.png', image)
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            # Build request
            payload = {
                "image_base64": image_base64,
                "confidence": self.confidence_threshold,
                "protected_labels": list(protected_labels)
            }

            data = json.dumps(payload).encode('utf-8')
            url = f"{self.api_url}/detect"

            req = urllib.request.Request(
                url,
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            # Send request
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.loads(response.read().decode('utf-8'))

            if not result.get('success'):
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

            return regions

        except Exception:
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
        """Get model file path. Check bundled first, then cache, then download."""
        filename = self._model_files.get(self.model_size, 'yolov8n-doclaynet.pt')
        print(f"[YOLODocLayNet] Looking for model: {filename}")

        # 1. Check bundled model (for PyInstaller)
        # PyInstaller sets sys._MEIPASS to temp extraction directory
        if hasattr(sys, '_MEIPASS'):
            bundled_path = os.path.join(sys._MEIPASS, 'resources', 'models', filename)
            bundled_path = os.path.abspath(bundled_path)
            print(f"[YOLODocLayNet] PyInstaller mode, checking: {bundled_path}")
            if os.path.exists(bundled_path):
                print(f"[YOLODocLayNet] Using bundled model: {bundled_path}")
                return bundled_path
            else:
                print(f"[YOLODocLayNet] Bundled model NOT found at: {bundled_path}")
                # List what's in _MEIPASS for debugging
                try:
                    meipass_contents = os.listdir(sys._MEIPASS)
                    print(f"[YOLODocLayNet] _MEIPASS contents: {meipass_contents[:20]}...")
                    resources_path = os.path.join(sys._MEIPASS, 'resources')
                    if os.path.exists(resources_path):
                        print(f"[YOLODocLayNet] resources/ contents: {os.listdir(resources_path)}")
                        models_path = os.path.join(resources_path, 'models')
                        if os.path.exists(models_path):
                            print(f"[YOLODocLayNet] resources/models/ contents: {os.listdir(models_path)}")
                except Exception as e:
                    print(f"[YOLODocLayNet] Error listing _MEIPASS: {e}")

        # 2. Check relative to source file (running from source)
        source_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'models', filename)
        source_path = os.path.abspath(source_path)
        print(f"[YOLODocLayNet] Checking source path: {source_path}")
        if os.path.exists(source_path):
            print(f"[YOLODocLayNet] Using source model: {source_path}")
            return source_path

        # 3. Check cache directory
        os.makedirs(self.MODEL_CACHE_DIR, exist_ok=True)
        local_path = os.path.join(self.MODEL_CACHE_DIR, filename)

        if os.path.exists(local_path):
            print(f"[YOLODocLayNet] Using cached model: {local_path}")
            return local_path

        # 4. Download if not exists
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


class YOLODocLayNetONNXDetector:
    """
    YOLO DocLayNet Detector using ONNX Runtime - Windows compatible.

    Uses ONNX Runtime instead of PyTorch for better Windows compatibility.
    No CUDA/PyTorch DLL dependencies.
    """

    # DocLayNet class names (11 classes)
    CLASS_NAMES = [
        'caption', 'footnote', 'formula', 'list-item', 'page-footer',
        'page-header', 'picture', 'section-header', 'table', 'text', 'title'
    ]

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

    ALL_LABELS = {
        'title', 'plain_text', 'table', 'figure',
        'figure_caption', 'isolate_formula', 'table_footnote', 'abandon'
    }

    def __init__(self,
                 confidence_threshold: float = 0.1,
                 protected_labels: Optional[Set[str]] = None,
                 imgsz: int = 1024):
        self.session = None
        self.confidence_threshold = confidence_threshold
        self.protected_labels = protected_labels or self.DEFAULT_PROTECTED_LABELS.copy()
        self.imgsz = imgsz
        self._model_loaded = False
        self._load_error = None

    def _get_model_path(self) -> str:
        """Get ONNX model path."""
        filename = 'yolov12s-doclaynet.onnx'  # Small model (35MB) - good balance of speed/accuracy
        print(f"[ONNX] Looking for model: {filename}")
        print(f"[ONNX] Current __file__: {__file__}")

        # 1. Check PyInstaller bundle
        if hasattr(sys, '_MEIPASS'):
            bundled_path = os.path.join(sys._MEIPASS, 'resources', 'models', filename)
            print(f"[ONNX] Checking PyInstaller bundle: {bundled_path}")
            if os.path.exists(bundled_path):
                print(f"[ONNX] Using bundled model: {bundled_path}")
                return bundled_path
            else:
                print(f"[ONNX] Bundle path not found")

        # 2. Check relative to source
        source_path = os.path.join(os.path.dirname(__file__), '..', 'resources', 'models', filename)
        source_path = os.path.abspath(source_path)
        print(f"[ONNX] Checking source path: {source_path}")
        if os.path.exists(source_path):
            print(f"[ONNX] Using source model: {source_path}")
            return source_path
        else:
            print(f"[ONNX] Source path not found")

        # 3. Check cache
        cache_path = os.path.expanduser(f"~/.cache/yolo-doclaynet/{filename}")
        print(f"[ONNX] Checking cache path: {cache_path}")
        if os.path.exists(cache_path):
            print(f"[ONNX] Using cached model: {cache_path}")
            return cache_path
        else:
            print(f"[ONNX] Cache path not found")

        # 4. Try to download from HuggingFace
        print(f"[ONNX] Model not found locally, attempting download from HuggingFace...")
        try:
            from huggingface_hub import hf_hub_download
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            downloaded_path = hf_hub_download(
                repo_id="hantian/yolo-doclaynet",
                filename=filename,
                local_dir=os.path.dirname(cache_path)
            )
            print(f"[ONNX] Model downloaded: {downloaded_path}")
            return downloaded_path
        except Exception as e:
            print(f"[ONNX] Download failed: {e}")

        raise FileNotFoundError(f"ONNX model not found: {filename}. Please ensure model exists at {source_path} or {cache_path}")

    def _load_model(self) -> bool:
        """Load ONNX model."""
        if self._model_loaded:
            return self.session is not None

        self._model_loaded = True

        try:
            import onnxruntime as ort
            model_path = self._get_model_path()
            print(f"[ONNX] Loading model: {model_path}")

            # Auto-select best provider: CUDA > CPU
            # Note: TensorRT disabled - doesn't support V100 SM 7.0 in some versions
            available_providers = ort.get_available_providers()

            # Configure session options for GPU optimization
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            # CRITICAL: Limit CPU threads to 80% to prevent system freeze
            # Without this, ONNX uses ALL cores causing 100% CPU on Windows
            cpu_count = os.cpu_count() or 1
            max_threads = max(1, int(cpu_count * 0.8))  # 80% of cores
            sess_options.intra_op_num_threads = max_threads
            sess_options.inter_op_num_threads = 1  # Single thread for op parallelism
            print(f"[ONNX] CPU threads limited to {max_threads}/{cpu_count} (80%)")

            # Try CUDA first (most reliable for V100)
            if 'CUDAExecutionProvider' in available_providers:
                providers = [
                    ('CUDAExecutionProvider', {
                        'device_id': 0,
                        'arena_extend_strategy': 'kSameAsRequested',
                        'cudnn_conv_algo_search': 'EXHAUSTIVE',
                        'do_copy_in_default_stream': True,
                    }),
                    'CPUExecutionProvider'
                ]
                print(f"[ONNX] Using GPU (CUDA)")
            else:
                providers = ['CPUExecutionProvider']
                print(f"[ONNX] Using CPU (no CUDA available)")

            self.session = ort.InferenceSession(model_path, sess_options, providers=providers)
            # Log actual provider being used
            actual_provider = self.session.get_providers()[0]
            print(f"[ONNX] Model loaded successfully - Provider: {actual_provider}")
            return True

        except ImportError as e:
            self._load_error = f"Missing onnxruntime: {e}"
            print(f"[ONNX] {self._load_error}")
            return False
        except Exception as e:
            self._load_error = str(e)
            print(f"[ONNX] Load error: {e}")
            return False

    def is_available(self) -> bool:
        if self.session is not None:
            return True
        return self._load_model()

    def get_load_error(self) -> Optional[str]:
        return self._load_error

    def _preprocess(self, image: np.ndarray) -> Tuple[np.ndarray, float, float]:
        """Preprocess image for YOLO inference."""
        import cv2
        h, w = image.shape[:2]

        # Calculate scale to fit imgsz
        scale = min(self.imgsz / h, self.imgsz / w)
        new_h, new_w = int(h * scale), int(w * scale)

        # Resize
        resized = cv2.resize(image, (new_w, new_h))

        # Pad to square
        pad_h = (self.imgsz - new_h) // 2
        pad_w = (self.imgsz - new_w) // 2
        padded = np.full((self.imgsz, self.imgsz, 3), 114, dtype=np.uint8)
        padded[pad_h:pad_h+new_h, pad_w:pad_w+new_w] = resized

        # BGR to RGB, HWC to CHW, normalize
        img = padded[:, :, ::-1].transpose(2, 0, 1)
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, 0)  # Add batch dimension

        return img, scale, (pad_w, pad_h)

    def _postprocess(self, output: np.ndarray, scale: float, pad: Tuple[int, int],
                     orig_shape: Tuple[int, int]) -> List[Tuple]:
        """Postprocess YOLO output to get detections."""
        # Output shape: (1, 15, 21504) = (batch, 4+11, num_anchors)
        # 4 = x, y, w, h; 11 = class scores
        predictions = output[0].T  # (21504, 15)

        # Get boxes and scores
        boxes = predictions[:, :4]  # x, y, w, h
        scores = predictions[:, 4:]  # class scores

        # Get best class for each detection
        class_ids = np.argmax(scores, axis=1)
        confidences = scores[np.arange(len(scores)), class_ids]

        # Filter by confidence
        mask = confidences > self.confidence_threshold
        boxes = boxes[mask]
        class_ids = class_ids[mask]
        confidences = confidences[mask]

        if len(boxes) == 0:
            return []

        # Convert xywh to xyxy
        x, y, w, h = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        x1 = x - w / 2
        y1 = y - h / 2
        x2 = x + w / 2
        y2 = y + h / 2

        # Remove padding and scale back
        pad_w, pad_h = pad
        x1 = (x1 - pad_w) / scale
        y1 = (y1 - pad_h) / scale
        x2 = (x2 - pad_w) / scale
        y2 = (y2 - pad_h) / scale

        # Clip to image bounds
        orig_h, orig_w = orig_shape
        x1 = np.clip(x1, 0, orig_w)
        y1 = np.clip(y1, 0, orig_h)
        x2 = np.clip(x2, 0, orig_w)
        y2 = np.clip(y2, 0, orig_h)

        # NMS
        detections = []
        for i in range(len(boxes)):
            detections.append((x1[i], y1[i], x2[i], y2[i], confidences[i], class_ids[i]))

        # Simple NMS
        detections = self._nms(detections, iou_threshold=0.5)

        return detections

    def _nms(self, detections: List[Tuple], iou_threshold: float = 0.5) -> List[Tuple]:
        """Non-maximum suppression."""
        if len(detections) == 0:
            return []

        # Sort by confidence
        detections = sorted(detections, key=lambda x: x[4], reverse=True)

        keep = []
        while detections:
            best = detections.pop(0)
            keep.append(best)

            detections = [d for d in detections
                         if self._iou(best[:4], d[:4]) < iou_threshold or best[5] != d[5]]

        return keep

    def _iou(self, box1: Tuple, box2: Tuple) -> float:
        """Calculate IoU between two boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0

    def detect(self, image: np.ndarray,
               protected_labels: Optional[Set[str]] = None,
               scale_factor: float = 1.0) -> List[ProtectedRegion]:
        """Detect layout regions using ONNX Runtime."""
        if not self._load_model():
            return []

        if protected_labels is None:
            protected_labels = self.protected_labels

        try:
            # Preprocess
            input_tensor, scale, pad = self._preprocess(image)
            orig_shape = image.shape[:2]

            # Run inference
            input_name = self.session.get_inputs()[0].name
            output = self.session.run(None, {input_name: input_tensor})[0]

            # Postprocess
            detections = self._postprocess(output, scale, pad, orig_shape)

            # Convert to ProtectedRegion
            regions = []
            for x1, y1, x2, y2, conf, cls_id in detections:
                label = self.CLASS_NAMES[int(cls_id)]
                internal_label = self.LABEL_MAPPING.get(label, label)

                if internal_label in protected_labels:
                    if scale_factor != 1.0:
                        x1 *= scale_factor
                        y1 *= scale_factor
                        x2 *= scale_factor
                        y2 *= scale_factor

                    regions.append(ProtectedRegion(
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        label=internal_label,
                        confidence=float(conf)
                    ))

            return regions

        except Exception as e:
            print(f"[ONNX] Detection error: {e}")
            import traceback
            traceback.print_exc()
            return []

    def detect_all(self, image: np.ndarray, scale_factor: float = 1.0) -> List[ProtectedRegion]:
        return self.detect(image, protected_labels=self.ALL_LABELS, scale_factor=scale_factor)

    def set_protected_labels(self, labels: Set[str]):
        self.protected_labels = labels & self.ALL_LABELS

    def set_confidence_threshold(self, threshold: float):
        self.confidence_threshold = max(0.0, min(1.0, threshold))


# Singleton instance for shared use
_yolo_onnx_instance: Optional[YOLODocLayNetONNXDetector] = None
_yolo_doclaynet_instance: Optional[YOLODocLayNetDetector] = None
_detector_instance: Optional[LayoutParserDetector] = None
_paddle_detector_instance: Optional[PPDocLayoutDetector] = None
_legacy_detector_instance: Optional[DocLayoutYOLO] = None
_remote_detector_instance: Optional[RemoteLayoutDetector] = None


def get_layout_detector() -> YOLODocLayNetONNXDetector:
    """Get shared ONNX detector instance - Windows compatible"""
    return get_yolo_onnx_detector()


def get_yolo_onnx_detector() -> YOLODocLayNetONNXDetector:
    """Get shared YOLODocLayNetONNXDetector instance - Windows compatible"""
    global _yolo_onnx_instance
    if _yolo_onnx_instance is None:
        _yolo_onnx_instance = YOLODocLayNetONNXDetector()
    return _yolo_onnx_instance


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
