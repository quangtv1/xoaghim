# Xóa Vết Ghim PDF

Ứng dụng desktop dùng AI để xóa vết ghim (staple marks) từ tài liệu PDF scan.

**Phiên bản:** 1.1.22 | **Tổ chức:** HUCE | **Framework:** PyQt5 | **Python 3.8+**

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
- **Undo (Ctrl+Z)** - Hoàn tác thao tác vùng chọn (tối đa 79 lần)
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
core/          (6 files, ~2,930 lines)
  ├── pdf_handler.py       # PDF I/O, caching
  ├── layout_detector.py   # AI detection (ONNX)
  ├── processor.py         # Staple removal logic
  ├── zone_optimizer.py    # Polygon algorithms
  └── config_manager.py    # Config persistence

ui/            (13 files, ~10,800 lines)
  ├── main_window.py       # Main orchestrator
  ├── continuous_preview.py # Multi-page preview
  ├── page_thumbnail_sidebar.py # Thumbnail navigation
  ├── settings_panel.py    # Zone config UI
  ├── compact_settings_toolbar.py # Icon toolbar
  └── ... (other UI components)

tests/         (6 files, 124 tests)
  └── test_*.py           # Unit tests
```

Tài liệu chi tiết: [docs/](docs/)
