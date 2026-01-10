# Xóa Vết Ghim PDF

Ứng dụng desktop để xóa vết ghim (staple marks) từ tài liệu PDF scan.

## Tính năng

- Xử lý đơn file hoặc batch (nhiều file)
- Preview song song: Gốc | Đích (realtime)
- Chọn vùng xử lý: 4 góc, 4 cạnh, tùy biến
- Bảo vệ dấu/chữ ký (màu đỏ/xanh)
- Lọc trang: tất cả/lẻ/chẵn
- Xuất PDF với chất lượng tùy chọn (72-300 DPI)

## Cài đặt

```bash
# Clone repo
git clone https://github.com/quangtv1/xoaghim.git
cd xoaghim

# Cài dependencies
pip install -r requirements.txt

# Chạy ứng dụng
python main.py
```

## Dependencies

- Python 3.8+
- PyQt5 >= 5.15.0
- PyMuPDF >= 1.20.0
- OpenCV >= 4.5.0
- NumPy >= 1.20.0
- Pillow >= 9.0.0

## Sử dụng

1. **Mở file/thư mục** - Kéo thả hoặc dùng menu Tệp tin
2. **Chọn vùng xử lý** - Click vào các góc/cạnh trong panel Chỉnh sửa
3. **Điều chỉnh thông số** - Rộng, Cao, Độ nhạy
4. **Nhấn Run** - Xử lý và xuất file

## Screenshots

![Xóa Vết Ghim PDF](screenshot.png)

## License

MIT License
