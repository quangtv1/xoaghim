# Xóa Vết Ghim PDF

Ứng dụng desktop dùng AI để xóa vết ghim (staple marks) từ tài liệu PDF scan.

**Phiên bản:** 1.1.18 | **Tổ chức:** HUCE | **Framework:** PyQt5 | **Python 3.8+**

## Tính Năng Nổi Bật

### Xử Lý File
- **Đơn/Batch** - Xử lý file riêng lẻ hoặc hàng loạt từ thư mục
- **Drag & Drop** - Hỗ trợ kéo thả trên macOS/Windows
- **Lọc trang** - Tất cả/lẻ/chẵn/trang hiện tại

### Chọn Vùng Xử Lý
- **8 Preset Zones** - 4 góc + 4 cạnh
- **Custom Draw Mode** - Vẽ vùng tùy chỉnh trên preview
- **Multi-page** - Áp dụng vùng cho nhiều trang cùng lúc
- **Persistent Config** - Lưu cấu hình qua các lần mở app

### Bảo Vệ Nội Dung
- **Dấu/Chữ ký** - Giữ nguyên màu đỏ/xanh
- **AI Layout Detection** - YOLO DocLayNet với ONNX Runtime
  - Tự động nhận diện: text, table, figure, caption
  - Loại trừ vùng bảo vệ khỏi xử lý

### Preview & Xuất File
- **Song song** - Gốc | Đích (realtime sync)
- **Sync scroll/zoom** - Đồng bộ giữa 2 panel
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

**Windows Build:** [XoaGhim-1.1.18-Windows.zip](https://github.com/quangtv1/xoaghim/releases/latest)

## Sử Dụng

1. Mở file/thư mục (drag & drop hoặc menu)
2. Chọn vùng: góc/cạnh hoặc vẽ tùy chỉnh
3. Toggle bảo vệ text (nếu cần)
4. Điều chỉnh: rộng, cao, độ nhạy
5. Nhấn Run → xuất file

## Cấu Trúc

```
core/          (6 files, ~2,930 lines)
  ├── pdf_handler.py       # PDF I/O, caching
  ├── layout_detector.py   # AI detection (ONNX)
  ├── processor.py         # Staple removal logic
  ├── zone_optimizer.py    # Polygon algorithms
  └── config_manager.py    # Config persistence

ui/            (12 files, ~10,313 lines)
  ├── main_window.py       # Main orchestrator
  ├── continuous_preview.py # Multi-page preview
  ├── settings_panel.py    # Zone config UI
  ├── compact_settings_toolbar.py # Icon toolbar
  └── ... (other UI components)

tests/         (6 files, 124 tests)
  └── test_*.py           # Unit tests
```

Tài liệu chi tiết: [docs/](docs/)
