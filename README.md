# Xóa Vết Ghim PDF

Ứng dụng desktop để xóa vết ghim (staple marks) từ tài liệu PDF scan.

**Phiên bản:** 1.1.16 | **Tổ chức:** HUCE

## Tính năng chính

### Xử lý file
- **Xử lý đơn file** - Mở và xử lý từng file PDF
- **Xử lý hàng loạt (Batch)** - Xử lý nhiều file PDF trong thư mục
- **Kéo thả file** - Hỗ trợ drag & drop trên cả macOS và Windows
- **Lọc trang** - Áp dụng cho tất cả/trang lẻ/trang chẵn

### Chọn vùng xử lý
- **Preset zones** - 4 góc, 4 cạnh của trang
- **Custom Zone Draw Mode** - Vẽ vùng xử lý tùy chỉnh trực tiếp trên preview
- **Multi-page zone selection** - Áp dụng vùng cho nhiều trang cùng lúc
- **Reset zones** - Popup "Xóa tất cả" với 3 tùy chọn:
  - Thủ công (preset + custom zones)
  - Tự động (text protection)
  - Tất cả

### Bảo vệ nội dung
- **Bảo vệ dấu/chữ ký** - Giữ nguyên màu đỏ/xanh
- **Nhận diện vùng bảo vệ (AI)** - Layout detection với ONNX Runtime
  - Sử dụng model YOLO DocLayNet
  - Tự động nhận diện text, table, figure, caption...
  - Loại trừ vùng bảo vệ khỏi xử lý

### Preview và xuất file
- **Preview song song** - Gốc | Đích (realtime)
- **Sync scroll/zoom** - Đồng bộ cuộn và zoom giữa 2 panel
- **Chế độ xem** - Liên tiếp hoặc từng trang
- **Xuất PDF** - DPI tùy chọn (72-300), nén JPEG

## Cài đặt

### Yêu cầu
- Python 3.8+
- PyQt5 >= 5.15.0
- PyMuPDF >= 1.20.0
- OpenCV >= 4.5.0
- ONNX Runtime >= 1.22.0
- Shapely >= 2.0.0

### Cài đặt từ source

```bash
# Clone repo
git clone https://github.com/quangtv1/xoaghim.git
cd xoaghim

# Cài dependencies
pip install -r requirements.txt

# Chạy ứng dụng
python main.py
```

### Tải bản build sẵn

- **Windows:** [XoaGhim-1.1.16-Windows.zip](https://github.com/quangtv1/xoaghim/releases/latest)
  - Giải nén và chạy `XoaGhim-1.1.16.exe`

## Sử dụng

1. **Mở file/thư mục** - Kéo thả hoặc dùng menu Tệp tin
2. **Chọn vùng xử lý** - Click vào các góc/cạnh hoặc vẽ vùng tùy chỉnh
3. **Bật bảo vệ text (tùy chọn)** - Check "Nhận diện vùng bảo vệ (tự động)"
4. **Điều chỉnh thông số** - Rộng, Cao, Độ nhạy
5. **Nhấn Run** - Xử lý và xuất file

## Screenshots

![Xóa Vết Ghim PDF](screenshot.png)

## Cấu trúc dự án

```
xoaghim/
├── main.py                    # Entry point
├── requirements.txt           # Dependencies
├── core/
│   ├── processor.py           # Thuật toán xóa vết ghim
│   ├── pdf_handler.py         # Đọc/ghi file PDF
│   ├── layout_detector.py     # AI layout detection (ONNX)
│   └── zone_optimizer.py      # Zone optimization
├── ui/
│   ├── main_window.py         # Cửa sổ chính
│   ├── continuous_preview.py  # Preview liên tục
│   ├── settings_panel.py      # Panel cài đặt
│   ├── zone_selector.py       # Chọn vùng (góc/cạnh/tùy biến)
│   ├── zone_item.py           # Zone kéo thả trên preview
│   └── batch_preview.py       # Danh sách file batch
└── resources/
    └── models/                # ONNX models
```

## License

MIT License
