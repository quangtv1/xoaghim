This file is a merged representation of a subset of the codebase, containing specifically included files, combined into a single document by Repomix.

# File Summary

## Purpose
This file contains a packed representation of a subset of the repository's contents that is considered the most important context.
It is designed to be easily consumable by AI systems for analysis, code review,
or other automated processes.

## File Format
The content is organized as follows:
1. This summary section
2. Repository information
3. Directory structure
4. Repository files (if enabled)
5. Multiple file entries, each consisting of:
  a. A header with the file path (## File: path/to/file)
  b. The full contents of the file in a code block

## Usage Guidelines
- This file should be treated as read-only. Any changes should be made to the
  original repository files, not this packed version.
- When processing this file, use the file path to distinguish
  between different files in the repository.
- Be aware that this file may contain sensitive information. Handle it with
  the same level of security as you would the original repository.

## Notes
- Some files may have been excluded based on .gitignore rules and Repomix's configuration
- Binary files are not included in this packed representation. Please refer to the Repository Structure section for a complete list of file paths, including binary files
- Only files matching these patterns are included: *.py
- Files matching patterns in .gitignore are excluded
- Files matching default ignore patterns are excluded
- Files are sorted by Git change count (files with more changes are at the bottom)

# Directory Structure
```
main.py
```

# Files

## File: main.py
```python
#!/usr/bin/env python3
"""
Xóa Vết Ghim PDF - Ứng dụng xóa vết ghim từ tài liệu scan
"""

import sys
import os

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Qt plugin path for Linux (Rocky/RHEL/CentOS) - must be before PyQt5 import
if sys.platform.startswith('linux'):
    try:
        import PyQt5
        pyqt5_path = PyQt5.__path__[0]
        qt5_lib = os.path.join(pyqt5_path, 'Qt5', 'lib')
        qt5_plugins = os.path.join(pyqt5_path, 'Qt5', 'plugins')

        if os.path.isdir(qt5_lib):
            current_ld = os.environ.get('LD_LIBRARY_PATH', '')
            if qt5_lib not in current_ld:
                os.environ['LD_LIBRARY_PATH'] = f"{qt5_lib}:{current_ld}"

        if os.path.isdir(qt5_plugins):
            os.environ['QT_PLUGIN_PATH'] = qt5_plugins
    except Exception:
        pass  # Silently ignore if PyQt5 path detection fails

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from ui.main_window import MainWindow


def main():
    # High DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    
    # Set application info
    app.setApplicationName("Xóa Vết Ghim PDF")
    app.setOrganizationName("HUCE")
    app.setApplicationVersion("1.0.0")
    
    # Set default font
    font = QFont("Segoe UI", 9)
    app.setFont(font)
    
    # Set style
    app.setStyle("Fusion")
    
    # Minimal Blue Theme - Gray dominant
    PRIMARY_COLOR = "#0068FF"  # Blue for accents only
    PRIMARY_HOVER = "#0052CC"
    PRIMARY_LIGHT = "#E3F2FD"
    BG_COLOR = "#F0F2F5"
    CARD_BG = "#FFFFFF"
    BORDER_COLOR = "#D1D5DB"
    TEXT_PRIMARY = "#1F2937"
    TEXT_SECONDARY = "#6B7280"
    TOOLBAR_BG = "#E5E7EB"  # Gray toolbar
    
    app.setStyleSheet(f"""
        * {{
            font-family: 'SF Pro Display', 'SF Pro', 'Segoe UI', 'Helvetica Neue', sans-serif;
            font-size: 13px;
        }}
        QMainWindow {{
            background-color: {BG_COLOR};
        }}
        /* Menu Bar Styles */
        QMenuBar {{
            background-color: #F9FAFB;
            border-bottom: 1px solid {BORDER_COLOR};
            padding: 2px 8px;
            min-height: 28px;
        }}
        QMenuBar::item {{
            padding: 6px 12px;
            background: transparent;
            border-radius: 4px;
        }}
        QMenuBar::item:selected {{
            background-color: #E5E7EB;
        }}
        QMenuBar::item:pressed {{
            background-color: #D1D5DB;
        }}
        QMenu {{
            background-color: white;
            border: 1px solid {BORDER_COLOR};
            border-radius: 4px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 8px 24px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: #E5E7EB;
        }}
        QMenu::separator {{
            height: 1px;
            background: #E5E7EB;
            margin: 4px 8px;
        }}
        /* Toolbar Styles */
        QToolBar {{
            background-color: white;
            border: none;
            border-bottom: 1px solid {BORDER_COLOR};
            spacing: 8px;
            padding: 6px 12px;
            min-height: 36px;
        }}
        QToolBar QLabel {{
            color: {TEXT_PRIMARY};
            font-weight: 500;
        }}
        QToolBar QToolButton {{
            background-color: #0043a5;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: 500;
            font-size: 13px;
        }}
        QToolBar QToolButton:hover {{
            background-color: #1790ff;
        }}
        QToolBar QToolButton:checked {{
            background-color: #1790ff;
        }}
        QToolBar QPushButton {{
            background-color: #0043a5;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: 600;
        }}
        QToolBar QPushButton:hover {{
            background-color: #1790ff;
        }}
        QToolBar QPushButton:disabled {{
            background-color: #D1D5DB;
            color: #9CA3AF;
        }}
        QGroupBox {{
            font-weight: 600;
            font-size: 12px;
            color: {TEXT_SECONDARY};
            border: 1px solid {BORDER_COLOR};
            margin-top: 14px;
            padding: 14px 10px 10px 10px;
            background-color: {CARD_BG};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            background-color: {CARD_BG};
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {BORDER_COLOR};
        }}
        QSlider::handle:horizontal {{
            background: {PRIMARY_COLOR};
            width: 14px;
            height: 14px;
            margin: -5px 0;
        }}
        QSlider::handle:horizontal:hover {{
            background: {PRIMARY_HOVER};
        }}
        QSlider::sub-page:horizontal {{
            background: {PRIMARY_COLOR};
        }}
        QProgressBar {{
            border: none;
            text-align: center;
            background-color: {BORDER_COLOR};
            color: {TEXT_PRIMARY};
        }}
        QProgressBar::chunk {{
            background-color: {PRIMARY_COLOR};
        }}
        QSpinBox, QLineEdit {{
            padding: 6px 10px;
            border: 1px solid {BORDER_COLOR};
            border-radius: 4px;
            background-color: white;
            color: {TEXT_PRIMARY};
        }}
        QSpinBox:focus, QLineEdit:focus {{
            border-color: {PRIMARY_COLOR};
        }}
        QPushButton {{
            padding: 6px 14px;
            border: none;
            background-color: white;
            color: {TEXT_PRIMARY};
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: #F9FAFB;
        }}
        QPushButton:pressed {{
            background-color: #F3F4F6;
        }}
        QCheckBox {{
            color: {TEXT_PRIMARY};
            spacing: 6px;
        }}
        QLabel {{
            color: {TEXT_PRIMARY};
        }}
        QScrollBar:vertical {{
            background: {BG_COLOR};
            width: 10px;
        }}
        QScrollBar::handle:vertical {{
            background: {BORDER_COLOR};
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: #9CA3AF;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
        QScrollBar:horizontal {{
            background: {BG_COLOR};
            height: 10px;
        }}
        QScrollBar::handle:horizontal {{
            background: {BORDER_COLOR};
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: #9CA3AF;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
        }}
        QStatusBar {{
            background-color: {CARD_BG};
            color: {TEXT_SECONDARY};
            border-top: 1px solid {BORDER_COLOR};
        }}
    """)
    
    # Create and show window
    window = MainWindow()
    window.show()
    
    # Fit view after showing
    window.preview.zoom_fit()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
```
