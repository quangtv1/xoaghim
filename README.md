# Xóa Vết Ghim PDF

Ứng dụng desktop dùng AI để xóa vết ghim (staple marks) từ tài liệu PDF scan.

**Phiên bản:** 1.1.22 | **Tổ chức:** HUCE | **Framework:** PyQt5 | **Python 3.8+** | **Ngày cập nhật:** 2026-01-26

## Tính Năng Nổi Bật

### Xử Lý File
- **Đơn/Batch** - Xử lý file riêng lẻ hoặc hàng loạt từ thư mục
- **Drag & Drop** - Hỗ trợ kéo thả trên macOS/Windows
- **Lọc trang** - Tất cả/lẻ/chẵn/trang hiện tại
- **Bộ lọc Sidebar** - Lọc file theo tên và số trang (batch mode)
- **Loading overlay** - Spinner khi mở file PDF lớn (>20 trang)
- **Auto-recovery** - Tự động khôi phục file/folder và vùng chọn khi crash

### Chọn Vùng Xử Lý
- **8 Preset Zones** - 4 góc + 4 cạnh
- **Custom Draw Mode** - Vẽ vùng tùy chỉnh trên preview
- **Hybrid Zone Sizing** - Góc dùng pixel cố định, cạnh dùng % chiều dài
- **Zone chung/riêng** - Vùng chung cho tất cả hoặc riêng từng file/trang
- **Undo (Ctrl+Z / Cmd+Z)** - Hoàn tác thao tác vùng chọn (tối đa 79 lần)
- **Draw Mode (Cmd+A / Alt+A)** - Kích hoạt chế độ vẽ vùng tùy chỉnh
- **Select Mode (Cmd+S / Alt+S)** - Kích hoạt chế độ chọn zone
- **Zoom (+, -, =)** - Phóng to, thu nhỏ, reset zoom
- **Phím Delete** - Xóa vùng chọn đang được chọn
- **Xóa vùng chọn** - Xóa chung/riêng, từng trang/cả thư mục
- **Bộ đếm Zone** - Hiển thị số zone chung và riêng trên thanh bottom
- **Persistent Config** - Lưu cấu hình và vùng chọn qua các lần mở app

### Bảo Vệ Nội Dung
- **Dấu/Chữ ký** - Giữ nguyên màu đỏ/xanh
- **AI Layout Detection** - YOLO DocLayNet với ONNX Runtime
  - Tự động nhận diện: text, table, figure, caption
  - Loại trừ vùng bảo vệ khỏi xử lý

### Preview & Xuất File
- **Song song** - Gốc | Đích (realtime sync)
- **Trang thu nhỏ** - Thumbnail sidebar với highlight trang hiện tại
- **Sync scroll/zoom** - Đồng bộ giữa 2 panel
- **Giữ zoom** - Batch mode giữ nguyên zoom khi chuyển file
- **Liên tiếp/Trang** - Chế độ xem lựa chọn
- **DPI 72-300** - Nén JPEG tùy chọn

## Cài Đặt

```bash
# Clone & setup
git clone https://github.com/quangtv1/xoaghim.git
cd xoaghim
pip install -r requirements.txt

# Run
python main.py
```

**Windows Build:** [XoaGhim-1.1.22-Windows.zip](https://github.com/quangtv1/xoaghim/releases/latest)

## Sử Dụng

1. Mở file/thư mục (drag & drop hoặc menu)
2. Chọn vùng: góc/cạnh hoặc vẽ tùy chỉnh
3. Toggle bảo vệ text (nếu cần)
4. Điều chỉnh: rộng, cao, độ nhạy
5. Nhấn Run → xuất file

## Cấu Trúc

```
core/          (8 modules, ~2,146 lines)
  ├── processor.py         # Staple removal engine (500+ LOC)
  ├── layout_detector.py   # AI detection YOLO/ONNX (500+ LOC)
  ├── pdf_handler.py       # PDF I/O with caching (223 LOC)
  ├── zone_optimizer.py    # Polygon algorithms (315 LOC)
  ├── config_manager.py    # Config persistence (271 LOC)
  ├── resource_manager.py  # CPU/RAM monitoring (118 LOC)
  ├── parallel_processor.py # Batch processing (300+ LOC)
  └── __init__.py

ui/            (14 modules, ~13,620 lines)
  ├── main_window.py                # Main orchestrator
  ├── continuous_preview.py         # Multi-page preview
  ├── settings_panel.py             # Zone config
  ├── compact_settings_toolbar.py   # Icon toolbar
  ├── zone_selector.py              # Zone picker
  └── ... (11 other UI components)

tests/         (6 files, 108 tests, 98%+ pass)
  ├── test_processor.py    # Core removal logic
  ├── test_zone_undo.py    # Undo/Redo
  ├── test_compact_toolbar.py # UI toolbar
  ├── test_geometry.py     # Polygon operations
  ├── test_layout_detector.py # AI detection
  └── test_zone_optimizer.py # Zone calculations
```

Tài liệu chi tiết: [docs/](docs/)
