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
│   ├── text_protection_dialog.py  # Dialog cài đặt text protection
│   ├── compact_toolbar_icons.py    # QPainter-based icon buttons for compact toolbar
│   └── compact_settings_toolbar.py # Compact icon-only settings toolbar widget
├── resources/
│   └── models/
│       └── yolov12s-doclaynet.onnx  # AI model
├── tests/
│   ├── test_layout_detector.py
│   ├── test_zone_optimizer.py
│   ├── test_processor.py
│   ├── test_geometry.py
│   └── test_compact_toolbar.py    # 31 tests for compact toolbar widgets
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

#### `ui/compact_toolbar_icons.py`
- **CompactIconButton:** Reusable QPainter-based icon button
  - Supports 20+ icon types: corners, edges, draw modes, filters, actions
  - Checkable and selected state management
  - Color states: normal (gray), hover (blue), selected/protect (blue/pink)
  - Fixed 38x38px size with rounded background option
  - Tooltip support and cursor feedback
- **CompactIconSeparator:** Vertical divider between button groups
  - Fixed 8x38px size
  - Light gray color (#D1D5DB)

#### `ui/compact_settings_toolbar.py`
- **CompactSettingsToolbar:** Icon-only toolbar for collapsed settings panel
  - Signals: `zone_toggled`, `filter_changed`, `draw_mode_changed`, `clear_zones`, `ai_detect_toggled`
  - Zone buttons: 4 corners + 4 edges (8 buttons total)
  - Draw mode buttons: Remove (-) and Protect (+) in exclusive group
  - Filter buttons: All, Odd, Even, Current Page in exclusive group
  - Action buttons: Clear zones, AI detect
  - State synchronization methods: `set_zone_state()`, `set_filter_state()`, `set_draw_mode_state()`, `set_ai_detect_state()`
  - Full sync from settings: `sync_from_settings(enabled_zones, filter_mode, draw_mode, ai_detect)`
  - White background (42px height), organized button groups with separators

## Keyboard Shortcuts

| Phím tắt | Chức năng | Vị trí |
|----------|----------|--------|
| Ctrl+O | Mở file | Menu Tệp tin |
| Ctrl+Enter | Xử lý (Clean button) | Main window |
| Ctrl+Plus | Phóng to preview | Bottom bar |
| Ctrl+Minus | Thu nhỏ preview | Bottom bar |

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

## Changelog v1.1.18 (Compact Toolbar)

### Compact Settings Toolbar
- **Collapsible toolbar** - Icon-only toolbar when settings panel is collapsed
  - Chevron button to toggle collapse/expand state
  - Synchronized state between main panel and toolbar
  - Initial load fix for icon centering with proper alignment
- **Zone toggle buttons** - 8 icon buttons for quick zone control
  - 4 corners: Top-left, Top-right, Bottom-left, Bottom-right
  - 4 edges: Top, Bottom, Left, Right
- **Draw mode buttons** - Custom draw zone controls
  - Minus (-) icon for remove zone
  - Plus (+) icon for protect zone
  - Exclusive selection (only one active at a time)
- **Filter buttons** - Page filter quick access
  - "All" (two overlapping pages icon)
  - "Odd" (page with "1" label)
  - "Even" (page with "2" label)
  - "Current page" (page with "*" label)
  - Exclusive selection group
- **Action buttons**
  - Trash icon for clear all zones
  - AI text icon for auto-detect protect zones
- **Visual design**
  - Gray base color (#6B7280)
  - Blue hover/selected state (#3B82F6)
  - Pink color for protect mode (#EC4899)
  - Light blue background for selected state (#DBEAFE)
  - 38x38px icon buttons with consistent sizing
  - Vertical separators between button groups
  - 42px fixed height toolbar with white background
- **QPainter-based icons** - Custom drawn icons for visual consistency

### Files created
- `ui/compact_toolbar_icons.py` (326 lines) - CompactIconButton and CompactIconSeparator classes
  - Custom paint engine for 20+ icon types
  - Hover and selection state management
  - Icon types: corners, edges, draw modes, filters, actions
- `ui/compact_settings_toolbar.py` (243 lines) - CompactSettingsToolbar widget
  - Zone state synchronization
  - Filter group management
  - Draw mode exclusive selection
  - Public API: `set_zone_state()`, `set_filter_state()`, `set_draw_mode_state()`, `set_ai_detect_state()`, `sync_from_settings()`
- `tests/test_compact_toolbar.py` (31 new tests) - Comprehensive test coverage
  - Icon button creation and state tests
  - Toolbar UI initialization tests
  - Signal emission tests
  - State synchronization tests
  - Draw mode exclusivity tests
  - Filter group exclusivity tests

### Keyboard Shortcuts (Updated)
- **Ctrl+Enter** - Trigger Clean button (processes PDF)
- **Ctrl+O** - Open file
- **Ctrl+Plus** - Zoom in
- **Ctrl+Minus** - Zoom out

### UI Integration
- CompactSettingsToolbar integrated into SettingsPanel
- State synchronization with main settings controls
- Signals bridge toolbar actions to main processing logic

---

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
*Cập nhật: 2026-01-16*
