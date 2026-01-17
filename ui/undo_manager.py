"""
Undo Manager - Quản lý undo/redo cho zone operations
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from collections import deque


@dataclass
class UndoAction:
    """Một action có thể undo"""
    action_type: str          # 'add', 'delete', 'edit'
    zone_id: str              # ID của zone (base_id, không có page suffix)
    page_idx: int             # Trang chứa zone (-1 nếu áp dụng tất cả trang)
    before_data: Optional[tuple] = None  # Dữ liệu trước (None nếu add)
    after_data: Optional[tuple] = None   # Dữ liệu sau (None nếu delete)
    zone_type: str = 'remove'  # 'remove' or 'protect'


class UndoManager:
    """
    Quản lý undo stack cho zone operations
    Giới hạn 79 actions
    """
    MAX_UNDO = 79

    def __init__(self):
        self._stack: deque[UndoAction] = deque(maxlen=self.MAX_UNDO)
        self._enabled = True  # Cho phép tạm dừng recording khi đang undo

    def push(self, action: UndoAction):
        """Lưu action mới vào stack"""
        if self._enabled:
            self._stack.append(action)

    def undo(self) -> Optional[UndoAction]:
        """Pop và trả về action để restore"""
        if self._stack:
            return self._stack.pop()
        return None

    def can_undo(self) -> bool:
        """Kiểm tra có thể undo không"""
        return len(self._stack) > 0

    def clear(self):
        """Xóa toàn bộ stack (khi load file mới)"""
        self._stack.clear()

    def set_enabled(self, enabled: bool):
        """Bật/tắt recording (tắt khi đang thực hiện undo)"""
        self._enabled = enabled

    def count(self) -> int:
        """Số lượng actions trong stack"""
        return len(self._stack)
