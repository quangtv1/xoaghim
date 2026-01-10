# Xóa Vết Ghim PDF - Codebase Summary

## Tổng Quan

**Tên ứng dụng:** Xóa Vết Ghim PDF
**Phiên bản:** 1.0.0
**Tổ chức:** HUCE
**Mục đích:** Ứng dụng desktop để xóa vết ghim (staple marks) từ tài liệu PDF scan

## Mô Tả Chi Tiết

Đây là ứng dụng desktop được xây dựng bằng Python và PyQt5, cho phép người dùng:

1. **Mở và xem file PDF** - Hỗ trợ xem liên tục hoặc từng trang
2. **Chọn vùng cần xử lý** - Các góc, cạnh hoặc vùng tùy chỉnh
3. **Xóa vết ghim tự động** - Sử dụng thuật toán xử lý ảnh OpenCV
4. **Xuất file PDF đã xử lý** - Với chất lượng có thể tùy chỉnh

### Tính Năng Chính

- **Xử lý đơn file** - Mở và xử lý từng file PDF riêng lẻ
- **Xử lý hàng loạt (Batch)** - Xử lý nhiều file PDF trong thư mục
- **Preview song song** - Hiển thị ảnh gốc và kết quả cạnh nhau
- **Chọn vùng trực quan** - Kéo thả vùng xử lý trên preview
- **Bảo vệ màu đỏ/xanh** - Giữ nguyên dấu và chữ ký
- **Lọc trang** - Áp dụng cho tất cả/trang lẻ/trang chẵn

## Cấu Trúc Dự Án

```
xoaghim/
├── main.py                 # Entry point, setup UI theme
├── requirements.txt        # Dependencies
├── run.bat                 # Windows launcher
├── run.sh                  # Unix launcher
├── core/
│   ├── __init__.py
│   ├── processor.py        # Thuật toán xóa vết ghim (StapleRemover)
│   └── pdf_handler.py      # Đọc/ghi file PDF (PDFHandler, PDFExporter)
├── ui/
│   ├── __init__.py
│   ├── main_window.py      # Cửa sổ chính, menu, xử lý logic
│   ├── continuous_preview.py  # Widget preview liên tục nhiều trang
│   ├── settings_panel.py   # Panel cài đặt vùng xử lý và đầu ra
│   ├── zone_selector.py    # Widget chọn vùng (góc/cạnh/tùy biến)
│   ├── zone_item.py        # Graphics item cho vùng kéo thả
│   ├── batch_preview.py    # Widget hiển thị danh sách file batch
│   └── preview_widget.py   # Widget preview cơ bản
├── resources/
│   ├── __init__.py
│   └── fit_width.png       # Icon fit width
├── models/
│   └── __init__.py
├── utils/
│   └── __init__.py
└── docs/
    └── codebase-summary.md # Tài liệu này
```

## Công Nghệ Sử Dụng

### Dependencies (requirements.txt)

| Package | Phiên bản | Mục đích |
|---------|-----------|----------|
| PyQt5 | >= 5.15.0 | GUI framework |
| PyMuPDF (fitz) | >= 1.20.0 | Đọc/ghi PDF |
| opencv-python | >= 4.5.0 | Xử lý ảnh |
| numpy | >= 1.20.0 | Xử lý mảng số |

### Tech Stack

- **Language:** Python 3
- **GUI Framework:** PyQt5 (Fusion style, custom Blue theme)
- **PDF Processing:** PyMuPDF (fitz)
- **Image Processing:** OpenCV (cv2), NumPy
- **Architecture:** Desktop standalone app

## Module Chi Tiết

### 1. Core Layer

#### `core/processor.py`
- **Zone (dataclass):** Định nghĩa vùng xử lý với tọa độ %, threshold
- **StapleRemover:** Class chính xử lý xóa vết ghim
  - `get_background_color()` - Lấy màu nền từ vùng giữa-phải
  - `is_red_or_blue()` - Phát hiện pixel đỏ/xanh để bảo vệ
  - `process_zone()` - Xử lý một vùng cụ thể
  - `process_image()` - Xử lý ảnh với nhiều vùng
- **PRESET_ZONES:** Các vùng preset (4 góc, 2 viền trái/phải)

**Thuật toán xử lý:**
1. Lấy màu nền từ vùng an toàn (giữa-phải trang)
2. Chuyển vùng cần xử lý sang grayscale
3. Tìm pixel tối hơn nền theo threshold
4. Loại trừ vùng chữ đen (gray < 80)
5. Loại trừ pixel màu đỏ/xanh (bảo vệ dấu, chữ ký)
6. Áp dụng morphological operations (close + dilate)
7. Đổ màu nền lên vùng artifact

#### `core/pdf_handler.py`
- **PDFHandler:** Đọc file PDF, render trang thành numpy array
  - `render_page()` - Render trang với DPI tùy chọn
  - Page cache để tối ưu hiệu suất
- **PDFExporter:** Xuất PDF đã xử lý
  - `export()` - Xuất với JPEG compression

### 2. UI Layer

#### `ui/main_window.py`
- **MainWindow:** Cửa sổ chính
  - Menu ribbon-style (Tệp tin, Xem, Chỉnh sửa, Cài đặt)
  - Bottom bar với điều khiển trang và zoom
  - Drag & drop support
- **ProcessThread:** Thread xử lý single file
- **BatchProcessThread:** Thread xử lý batch
- **HoverMenuButton:** Button menu với hover behavior

#### `ui/continuous_preview.py`
- **ContinuousPreviewWidget:** Widget preview song song (Gốc | Đích)
- **ContinuousPreviewPanel:** Panel preview với zones overlay
- **ContinuousGraphicsView:** GraphicsView với sync scroll/zoom

#### `ui/settings_panel.py`
- **SettingsPanel:** Panel cài đặt 3 cột
  - Cột 1: Chọn vùng (ZoneSelectorWidget)
  - Cột 2: Thông số (rộng, cao, độ nhạy)
  - Cột 3: Đầu ra (DPI, thư mục, tên file)

#### `ui/zone_selector.py`
- **PaperIcon:** Icon trang giấy với zones có thể click
- **ZoneSelectorWidget:** Widget tổng hợp (Góc | Cạnh | Tùy biến)

### 3. Resources

- `resources/fit_width.png` - Icon cho nút fit width

## Luồng Xử Lý Chính

```
User mở file PDF
      ↓
PDFHandler render các trang → numpy arrays
      ↓
MainWindow hiển thị trên ContinuousPreviewWidget
      ↓
User chọn vùng xử lý (zones)
      ↓
User nhấn "Run"
      ↓
ProcessThread xử lý từng trang:
  → StapleRemover.process_image(image, zones)
      ↓
PDFExporter.export() → File PDF output
      ↓
Hiển thị dialog hoàn thành
```

## Cài Đặt Mặc Định

| Cài đặt | Giá trị mặc định |
|---------|------------------|
| DPI xuất | 250 |
| Vùng mặc định | Góc trên trái (12% x 12%) |
| Threshold | 5 |
| Pattern tên file | `{gốc}_clean.pdf` |
| Bảo vệ màu đỏ/xanh | Có |
| Max preview pages | 20 |

## Điểm Đáng Chú Ý

1. **High DPI Support** - Hỗ trợ màn hình độ phân giải cao
2. **Debounced Processing** - Delay 300ms trước khi xử lý lại preview
3. **Page Cache** - Cache tối đa 10 trang để tối ưu bộ nhớ
4. **Per-page Zones** - Hỗ trợ vùng độc lập cho từng trang (chế độ 'none')
5. **Sync Scroll/Zoom** - Đồng bộ cuộn và zoom giữa 2 panel preview

## Hạn Chế / Cần Cải Thiện

1. Chế độ xem một trang chưa hoàn thiện (hiển thị "sẽ cập nhật")
2. Chưa có GPU acceleration (OpenCV CPU only)
3. Chưa có undo/redo
4. Chưa có preset profiles cho các loại tài liệu khác nhau

---
*Cập nhật: 2026-01-10*
