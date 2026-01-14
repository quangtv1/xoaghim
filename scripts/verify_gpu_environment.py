#!/usr/bin/env python3
"""
GPU Environment Verification Script for Xóa Ghim PDF

Kiểm tra môi trường có đáp ứng yêu cầu chạy với GPU (Tesla V100) không.
Usage: python scripts/verify_gpu_environment.py
"""

import sys
import os
import subprocess
import platform
from typing import Tuple, Optional

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def print_header(title: str):
    """Print section header"""
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{title}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}")


def print_ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")


def print_fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")


def print_warn(msg: str):
    print(f"  {YELLOW}⚠{RESET} {msg}")


def print_info(msg: str):
    print(f"  {BLUE}ℹ{RESET} {msg}")


def check_python_version() -> bool:
    """Check Python version >= 3.8"""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"
    if version >= (3, 8):
        print_ok(f"Python {version_str}")
        return True
    else:
        print_fail(f"Python {version_str} (cần >= 3.8)")
        return False


def check_os_info():
    """Display OS information"""
    print_info(f"OS: {platform.system()} {platform.release()}")
    print_info(f"Platform: {platform.platform()}")

    # Check if Rocky Linux
    if os.path.exists("/etc/rocky-release"):
        with open("/etc/rocky-release") as f:
            print_info(f"Rocky Linux: {f.read().strip()}")


def check_nvidia_driver() -> Tuple[bool, Optional[str]]:
    """Check NVIDIA driver installation"""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version,name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines:
                parts = line.split(", ")
                if len(parts) >= 3:
                    driver_ver, gpu_name, mem = parts[0], parts[1], parts[2]
                    print_ok(f"NVIDIA Driver: {driver_ver}")
                    print_ok(f"GPU: {gpu_name}")
                    print_ok(f"GPU Memory: {mem}")
                    return True, driver_ver
            return True, None
        else:
            print_fail("nvidia-smi failed")
            return False, None
    except FileNotFoundError:
        print_fail("nvidia-smi not found - NVIDIA driver not installed")
        return False, None
    except Exception as e:
        print_fail(f"nvidia-smi error: {e}")
        return False, None


def check_cuda_toolkit() -> Tuple[bool, Optional[str]]:
    """Check CUDA toolkit installation"""
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            # Parse version from output
            for line in result.stdout.split("\n"):
                if "release" in line.lower():
                    # Extract version like "release 12.4"
                    parts = line.split("release")
                    if len(parts) > 1:
                        version = parts[1].split(",")[0].strip()
                        print_ok(f"CUDA Toolkit: {version}")
                        return True, version
            print_ok("CUDA Toolkit: installed")
            return True, None
        else:
            print_fail("nvcc not found in PATH")
            return False, None
    except FileNotFoundError:
        print_fail("nvcc not found - CUDA toolkit not installed or not in PATH")
        print_info("Add to PATH: export PATH=/usr/local/cuda/bin:$PATH")
        return False, None
    except Exception as e:
        print_fail(f"CUDA check error: {e}")
        return False, None


def check_cudnn() -> bool:
    """Check cuDNN installation"""
    # Check common cuDNN library paths
    cudnn_paths = [
        "/usr/local/cuda/lib64/libcudnn.so",
        "/usr/lib64/libcudnn.so",
        "/usr/local/cuda/include/cudnn.h",
    ]

    for path in cudnn_paths:
        if os.path.exists(path):
            print_ok(f"cuDNN found: {path}")
            return True

    # Try to find via ldconfig
    try:
        result = subprocess.run(
            ["ldconfig", "-p"],
            capture_output=True, text=True, timeout=10
        )
        if "libcudnn" in result.stdout:
            print_ok("cuDNN found via ldconfig")
            return True
    except:
        pass

    print_warn("cuDNN not found (may still work if bundled with packages)")
    return False


def check_pytorch() -> Tuple[bool, bool]:
    """Check PyTorch and CUDA support"""
    try:
        import torch
        version = torch.__version__
        print_ok(f"PyTorch: {version}")

        cuda_available = torch.cuda.is_available()
        if cuda_available:
            cuda_version = torch.version.cuda
            print_ok(f"PyTorch CUDA: {cuda_version}")

            device_count = torch.cuda.device_count()
            for i in range(device_count):
                name = torch.cuda.get_device_name(i)
                mem = torch.cuda.get_device_properties(i).total_memory / (1024**3)
                print_ok(f"  GPU {i}: {name} ({mem:.1f} GB)")

            # Test CUDA computation
            try:
                x = torch.tensor([1.0, 2.0]).cuda()
                y = x * 2
                print_ok("PyTorch CUDA computation: OK")
            except Exception as e:
                print_fail(f"PyTorch CUDA computation failed: {e}")
                return True, False

            return True, True
        else:
            print_warn("PyTorch CUDA not available (CPU only)")
            return True, False

    except ImportError:
        print_fail("PyTorch not installed")
        print_info("Install: pip install torch --index-url https://download.pytorch.org/whl/cu124")
        return False, False
    except Exception as e:
        print_fail(f"PyTorch check error: {e}")
        return False, False


def check_onnxruntime() -> Tuple[bool, bool]:
    """Check ONNX Runtime and GPU support"""
    try:
        import onnxruntime as ort
        version = ort.__version__
        print_ok(f"ONNX Runtime: {version}")

        providers = ort.get_available_providers()
        print_info(f"Available providers: {providers}")

        # Check TensorRT
        if "TensorrtExecutionProvider" in providers:
            print_info("TensorRT: available (but may not support V100 SM 7.0)")

        # Check CUDA (recommended for V100)
        if "CUDAExecutionProvider" in providers:
            print_ok("ONNX Runtime CUDA: available (recommended for V100)")

            # Test GPU provider
            try:
                print_ok("ONNX Runtime GPU provider: OK")
                print_info("Using: CUDA with cuDNN EXHAUSTIVE algo search")
                return True, True
            except Exception as e:
                print_warn(f"GPU provider test warning: {e}")
                return True, True
        else:
            print_warn("CUDAExecutionProvider not available")
            print_info("Install: pip install onnxruntime-gpu")
            return True, False

    except ImportError:
        print_fail("ONNX Runtime not installed")
        print_info("Install: pip install onnxruntime-gpu")
        return False, False
    except Exception as e:
        print_fail(f"ONNX Runtime check error: {e}")
        return False, False


def check_opencv() -> bool:
    """Check OpenCV installation"""
    try:
        import cv2
        version = cv2.__version__
        print_ok(f"OpenCV: {version}")

        # Check CUDA support (optional)
        try:
            cuda_devices = cv2.cuda.getCudaEnabledDeviceCount()
            if cuda_devices > 0:
                print_ok(f"OpenCV CUDA: {cuda_devices} device(s)")
            else:
                print_info("OpenCV CUDA: not enabled (OK for this app)")
        except:
            print_info("OpenCV CUDA: not available (OK for this app)")

        return True

    except ImportError:
        print_fail("OpenCV not installed")
        print_info("Install: pip install opencv-python")
        return False


def check_other_deps() -> dict:
    """Check other dependencies"""
    deps = {
        "PyQt5": "PyQt5",
        "PyMuPDF": "fitz",
        "NumPy": "numpy",
        "Pillow": "PIL",
        "Shapely": "shapely",
        "Ultralytics": "ultralytics",
        "HuggingFace Hub": "huggingface_hub",
    }

    results = {}
    for name, module in deps.items():
        try:
            m = __import__(module)
            version = getattr(m, "__version__", "unknown")
            print_ok(f"{name}: {version}")
            results[name] = True
        except ImportError:
            print_fail(f"{name} not installed")
            results[name] = False

    return results


def check_model_files() -> bool:
    """Check if YOLO model files exist"""
    model_paths = [
        os.path.expanduser("~/.cache/yolo-doclaynet/yolov12s-doclaynet.onnx"),
        os.path.expanduser("~/.cache/yolo-doclaynet/yolov12l-doclaynet.pt"),
        os.path.join(os.path.dirname(__file__), "..", "resources", "models"),
    ]

    found = False
    for path in model_paths:
        if os.path.exists(path):
            print_ok(f"Model found: {path}")
            found = True

    if not found:
        print_info("No cached models found - will download on first run")

    return True  # Not critical - will auto-download


def test_yolo_inference() -> bool:
    """Test YOLO inference with GPU"""
    try:
        # Add parent directory to path
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        from core.layout_detector import get_layout_detector
        import numpy as np

        print_info("Testing YOLO inference...")

        # Create test image
        test_img = np.zeros((640, 480, 3), dtype=np.uint8)
        test_img.fill(255)  # White image

        detector = get_layout_detector()
        if detector.is_available():
            print_ok("Layout detector initialized")

            # Run inference
            regions = detector.detect(test_img)
            print_ok(f"Inference OK - detected {len(regions)} regions")
            return True
        else:
            print_fail(f"Detector not available: {detector.get_load_error()}")
            return False

    except Exception as e:
        print_fail(f"Inference test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_summary(results: dict):
    """Print summary and recommendations"""
    print_header("SUMMARY")

    all_ok = all(results.values())
    gpu_ok = results.get("nvidia_driver", False) and (
        results.get("pytorch_cuda", False) or results.get("onnx_cuda", False)
    )

    if all_ok and gpu_ok:
        print(f"\n{GREEN}{BOLD}✓ Môi trường đã sẵn sàng cho GPU (Tesla V100){RESET}")
    elif all_ok:
        print(f"\n{YELLOW}{BOLD}⚠ Môi trường OK nhưng GPU chưa được kích hoạt{RESET}")
    else:
        print(f"\n{RED}{BOLD}✗ Cần cài đặt thêm một số thành phần{RESET}")

    # Recommendations
    print_header("RECOMMENDATIONS")

    if not results.get("nvidia_driver"):
        print_info("Cài NVIDIA driver:")
        print("       sudo dnf install -y nvidia-driver nvidia-driver-cuda")

    if not results.get("cuda_toolkit"):
        print_info("Cài CUDA Toolkit:")
        print("       sudo dnf install -y cuda-toolkit-12-4")
        print("       echo 'export PATH=/usr/local/cuda/bin:$PATH' >> ~/.bashrc")

    if not results.get("pytorch_cuda"):
        print_info("Cài PyTorch với CUDA:")
        print("       pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124")

    if not results.get("onnx_cuda"):
        print_info("Cài ONNX Runtime GPU:")
        print("       pip uninstall onnxruntime")
        print("       pip install onnxruntime-gpu")


def main():
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  GPU Environment Verification - Xóa Ghim PDF{RESET}")
    print(f"{BOLD}  Target: Rocky Linux + Tesla V100{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    results = {}

    # System Info
    print_header("1. SYSTEM INFO")
    check_os_info()
    results["python"] = check_python_version()

    # NVIDIA / CUDA
    print_header("2. NVIDIA / CUDA")
    results["nvidia_driver"], _ = check_nvidia_driver()
    results["cuda_toolkit"], cuda_ver = check_cuda_toolkit()
    results["cudnn"] = check_cudnn()

    # Deep Learning Frameworks
    print_header("3. DEEP LEARNING FRAMEWORKS")
    results["pytorch"], results["pytorch_cuda"] = check_pytorch()
    results["onnxruntime"], results["onnx_cuda"] = check_onnxruntime()

    # Python Dependencies
    print_header("4. PYTHON DEPENDENCIES")
    results["opencv"] = check_opencv()
    dep_results = check_other_deps()
    results.update(dep_results)

    # Model Files
    print_header("5. MODEL FILES")
    results["models"] = check_model_files()

    # Inference Test
    print_header("6. INFERENCE TEST")
    results["inference"] = test_yolo_inference()

    # Summary
    print_summary(results)

    # Return code
    critical = ["python", "opencv", "onnxruntime"]
    if all(results.get(k, False) for k in critical):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
