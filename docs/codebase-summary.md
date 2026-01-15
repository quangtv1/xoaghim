# Xóa Vết Ghim PDF - Codebase Summary

## Tổng Quan

**Tên ứng dụng:** Xóa Vết Ghim PDF
**Phiên bản:** 1.1.17
**Tổ chức:** HUCE
**Mục đích:** Ứng dụng desktop để xóa vết ghim (staple marks) từ tài liệu PDF scan

## Tính Năng Chi Tiết

### 1. Xử lý file
- Xử lý đơn file hoặc batch (nhiều file)
- Drag & drop hỗ trợ cả macOS và Windows
- Lọc trang: tất cả/lẻ/chẵn

### 2. Chọn vùng xử lý
- **Preset zones:** 4 góc, 4 cạnh của trang
- **Custom Zone Draw Mode:** Vẽ vùng xử lý tùy chỉnh trực tiếp trên preview
- **Multi-page zone selection:** Áp dụng vùng cho nhiều trang cùng lúc
- **Zone config persistence:** Lưu cấu hình vùng (enabled, sizes, threshold, filter) qua:
  - Đổi file/thư mục
  - Tắt/mở app
- **2-click zone reset:** Click bỏ chọn → click chọn lại = reset về kích thước mặc định
- **Reset zones popup:** 3 tùy chọn
  - Thủ công (preset + custom zones)
  - Tự động (text protection)
  - Tất cả

### 3. Bảo vệ nội dung
- Bảo vệ dấu/chữ ký (màu đỏ/xanh)
- **AI Layout Detection:**
  - Model YOLO DocLayNet (ONNX Runtime)
  - Tự động nhận diện: text, table, figure, caption, list, title, header, footer...
  - Loại trừ vùng bảo vệ khỏi xử lý

### 4. Preview và xuất file
- Preview song song: Gốc | Đích (realtime)
- Sync scroll/zoom giữa 2 panel
- Chế độ xem: liên tiếp hoặc từng trang
- Xuất PDF: DPI 72-300, nén JPEG

## Cấu Trúc Dự Án

```
xoaghim/
├── main.py                    # Entry point, UI theme setup
├── requirements.txt           # Dependencies
├── XoaGhim-1.1.16.spec        # PyInstaller spec (Windows)
├── core/
│   ├── processor.py           # Thuật toán xóa vết ghim (StapleRemover)
│   ├── pdf_handler.py         # Đọc/ghi PDF (PDFHandler, PDFExporter)
│   ├── layout_detector.py     # AI layout detection (ONNX)
│   ├── zone_optimizer.py      # Zone optimization utilities
│   └── config_manager.py      # Zone config persistence (JSON)
├── ui/
│   ├── main_window.py         # Cửa sổ chính, menu, drag & drop
│   ├── continuous_preview.py  # Preview liên tục với zones overlay
│   ├── settings_panel.py      # Panel cài đặt 3 cột
│   ├── zone_selector.py       # Widget chọn vùng (góc/cạnh/tùy biến)
│   ├── zone_item.py           # Graphics item cho vùng kéo thả
│   ├── batch_preview.py       # Danh sách file batch
│   ├── preview_widget.py      # Preview widget cơ bản
│   └── text_protection_dialog.py  # Dialog cài đặt text protection
├── resources/
│   └── models/
│       └── yolov12s-doclaynet.onnx  # AI model
├── tests/
│   ├── test_layout_detector.py
│   └── test_zone_optimizer.py
└── .github/
    └── workflows/
        └── build-windows.yml  # GitHub Actions build
```

## Tech Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.8+ |
| GUI Framework | PyQt5 | >= 5.15.0 |
| PDF Processing | PyMuPDF (fitz) | >= 1.20.0 |
| Image Processing | OpenCV | >= 4.5.0 |
| AI Inference | ONNX Runtime | >= 1.22.0 |
| Geometry | Shapely | >= 2.0.0 |
| Arrays | NumPy | >= 1.20.0 |

## Module Chi Tiết

### Core Layer

#### `core/processor.py`
- **Zone (dataclass):** Vùng xử lý với tọa độ %, threshold
- **StapleRemover:** Class xử lý xóa vết ghim
  - `get_background_color()` - Lấy màu nền
  - `is_red_or_blue()` - Phát hiện pixel đỏ/xanh
  - `process_zone()` - Xử lý một vùng
  - `process_image()` - Xử lý ảnh với nhiều vùng
- **PRESET_ZONES:** 4 góc, 4 cạnh

**Thuật toán:**
1. Lấy màu nền từ vùng an toàn
2. Chuyển vùng sang grayscale
3. Tìm pixel tối hơn nền theo threshold
4. Loại trừ vùng chữ đen (gray < 80)
5. Loại trừ pixel đỏ/xanh (bảo vệ dấu)
6. Áp dụng morphological operations
7. Đổ màu nền lên vùng artifact

#### `core/layout_detector.py`
- **LayoutDetector:** AI-powered layout detection
  - Model: YOLO DocLayNet (ONNX)
  - 11 categories: text, title, list, table, figure...
  - Lazy loading để tối ưu memory
- **ProtectedRegion (dataclass):** Vùng được bảo vệ

#### `core/pdf_handler.py`
- **PDFHandler:** Đọc PDF, render trang
- **PDFExporter:** Xuất PDF với compression

### UI Layer

#### `ui/main_window.py`
- **MainWindow:** Cửa sổ chính
  - Menu ribbon-style
  - Bottom bar (trang, zoom)
  - Drag & drop (macOS + Windows)
- **ProcessThread:** Thread xử lý single file
- **BatchProcessThread:** Thread xử lý batch

#### `ui/continuous_preview.py`
- **ContinuousPreviewWidget:** Preview song song
- **ContinuousPreviewPanel:** Panel với zones overlay
- **ContinuousGraphicsView:** View với sync scroll/zoom
- Custom zone drawing mode

#### `ui/settings_panel.py`
- **SettingsPanel:** Panel cài đặt 3 cột
  - Cột 1: Chọn vùng (ZoneSelectorWidget)
  - Cột 2: Thông số (rộng, cao, độ nhạy)
  - Cột 3: Đầu ra (DPI, thư mục, tên file)
- "Xóa tất cả" popup với 3 options
- Text protection checkbox

#### `ui/zone_selector.py`
- **PaperIcon:** Icon trang giấy với zones
- **ZoneSelectorWidget:** Widget tổng hợp
- DPI-aware rendering (cosmetic pen)

#### `ui/zone_item.py`
- **ZoneItem:** Graphics item kéo thả trên preview
- Resize handles
- Multi-page selection support

## Cài Đặt Mặc Định

| Cài đặt | Giá trị |
|---------|---------|
| DPI xuất | 250 |
| Vùng mặc định | Góc trên trái (12% x 12%) |
| Threshold | 5 |
| Pattern tên file | `{gốc}_clean.pdf` |
| Bảo vệ màu đỏ/xanh | Có |
| Max preview pages | 20 |

## Build & Release

### Windows Build
```bash
# Tạo tag để trigger GitHub Actions
git tag v1.1.16
git push origin v1.1.16
```

GitHub Actions sẽ:
1. Build với PyInstaller (onedir mode)
2. Bundle ONNX Runtime DLLs
3. Bundle VC++ Runtime DLLs
4. Upload artifact và tạo release

### Output
- `XoaGhim-1.1.16-Windows.zip`
- Chứa: exe, DLLs, resources/models

## Changelog v1.1.17

- **Zone config persistence:** Lưu cấu hình vùng vào JSON
  - macOS: `~/Library/Application Support/XoaGhim/config.json`
  - Windows: `%APPDATA%/XoaGhim/config.json`
  - Linux: `~/.config/XoaGhim/config.json`
- **2-click zone reset:** Click bỏ chọn → click chọn lại = reset về size mặc định
- File mới: `core/config_manager.py`

## Changelog v1.1.16

- Fix zone icon border dày trên Windows high DPI
- Fix Windows drag & drop (file:///C:/path format)
- Dropdown arrow icon cho DPI và Nén comboboxes
- "Xóa tất cả" popup với 3 tùy chọn (Thủ công/Tự động/Tất cả)
- Custom Zone Draw Mode
- AI Layout Detection với ONNX Runtime
- Multi-page zone selection

---
*Cập nhật: 2026-01-15*
