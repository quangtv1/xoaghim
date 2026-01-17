# XoaGhim PDF - UI Directory Scout Report

**Generated:** January 17, 2026  
**Scope:** `/Users/quangtv/app/xoaghim/ui/` directory  
**Python Files:** 12  
**Total Lines:** 10,313  

## Reports Generated

This scout mission has produced comprehensive documentation about the PyQt5 UI codebase:

### 1. **Detailed Scout Report**
📄 `plans/reports/scout-260117-ui-directory.md` (548 lines, 16KB)

**Contains:**
- Executive summary of architecture
- Detailed analysis of all 12 Python files
- Class descriptions and responsibilities
- Signal flow diagrams
- Widget hierarchy
- Design patterns used
- Color scheme documentation
- Performance considerations
- Unresolved questions

**Best for:** Deep understanding of each component, architecture decisions, technical implementation details

---

### 2. **Quick Reference Guide**
📄 `plans/reports/scout-260117-ui-quick-reference.md` (228 lines, 7.3KB)

**Contains:**
- File/class lookup table
- Class relationships diagram
- Critical signal paths
- Module dependencies
- Color constants (RGB values)
- Threading model overview
- Common patterns reference
- Configuration & persistence details
- Testing entry points
- Extension points for development

**Best for:** Quick lookup, understanding data flow, finding classes/signals, making modifications

---

## Key Findings

### Application Architecture
- **Main Entry:** `main_window.py` (2,828 lines) - Central orchestrator
- **Preview System:** `continuous_preview.py` (1,200+ lines) - Multi-page with AI detection
- **Zone Management:** `zone_selector.py` + `zone_item.py` - Interactive overlays
- **Batch Processing:** `batch_sidebar.py` - File management UI
- **Settings:** `settings_panel.py` - Configuration and persistence

### Custom Widgets (8 total)
1. **PaperIcon** - Stacked paper icon with clickable zones
2. **ZoneSelectorWidget** - Three-mode zone selector
3. **ZoneItem** - Draggable/resizable overlay
4. **ContinuousPreviewWidget** - Multi-page scrolling preview
5. **CompactIconButton** - Custom-painted toolbar buttons
6. **BatchSidebar** - File list with page counts
7. **SpinnerWidget** - Animated loading indicator
8. **TextProtectionDialog** - AI settings popup

### Design Patterns
- Signal/slot architecture for loose coupling
- QPainter for custom icons and graphics
- QGraphicsItem for interactive overlays
- Threading for CPU-intensive tasks
- Synchronized views for dual preview
- Event filtering for global interactions

### Color Scheme
- **Blue (#3B82F6)** - Primary actions, removal zones
- **Pink (#F472B6)** - Protection zones
- **Gray (#6B7280)** - Inactive elements
- **Light Gray (#E5E7EB)** - Backgrounds

---

## Quick Navigation

### By Component
| Component | Files | Purpose |
|-----------|-------|---------|
| **Main Window** | main_window.py | Application orchestrator |
| **Preview** | continuous_preview.py, preview_widget.py | Image display & zones |
| **Zone Selection** | zone_selector.py, zone_item.py | User zone management |
| **Batch Mode** | batch_sidebar.py, batch_preview.py | Multi-file processing |
| **Settings** | settings_panel.py, text_protection_dialog.py | Configuration UI |
| **Toolbar** | compact_settings_toolbar.py, compact_toolbar_icons.py | Collapsed UI |

### By Functionality
| Functionality | Key Files | Key Classes |
|---------------|-----------|-------------|
| **PDF Processing** | main_window.py | ProcessThread, BatchProcessThread |
| **Zone Management** | zone_selector.py, zone_item.py | ZoneSelectorWidget, ZoneItem |
| **File Selection** | batch_sidebar.py | BatchSidebar, SidebarFileList |
| **AI Detection** | continuous_preview.py | DetectionRunner |
| **Synchronized Views** | preview_widget.py | SyncGraphicsView |
| **Custom Icons** | compact_toolbar_icons.py | CompactIconButton |

---

## Signal Flow Summary

### Zone Selection → Preview Update
```
Zone clicked in settings 
  → ZoneSelectorWidget.zone_toggled 
  → SettingsPanel.zones_changed 
  → MainWindow._on_zones_changed 
  → ContinuousPreviewWidget.show_zones()
```

### Zone Drawn in Preview → Settings Update
```
User draws zone in preview 
  → ContinuousPreviewWidget.rect_drawn 
  → MainWindow._on_rect_drawn_from_preview 
  → SettingsPanel.add_custom_zone()
```

### File Selected → Preview Reloaded
```
File clicked in sidebar 
  → MainWindow._on_sidebar_file_selected 
  → Load PDF pages 
  → ContinuousPreviewWidget.set_images() 
  → Apply current zones
```

---

## For Developers

### Starting Point
Start with `scout-260117-ui-quick-reference.md` for:
- How to find what you're looking for
- Class relationships
- Signal paths to trace bugs

Then dive into `scout-260117-ui-directory.md` for:
- Detailed implementation of specific component
- Design decisions and rationale
- Related classes and dependencies

### Common Tasks

**I want to add a new zone type:**
→ See `zone_item.py` (ZoneItem class) and `zone_selector.py` (ZoneSelectorWidget)

**I want to modify the toolbar:**
→ See `compact_settings_toolbar.py` and `compact_toolbar_icons.py`

**I want to understand zone persistence:**
→ See `settings_panel.py` (_load_saved_config method) and imports of config_manager

**I want to add a new preview mode:**
→ See `continuous_preview.py` (ContinuousPreviewWidget._view_mode property)

**I want to track down a signal connection:**
→ Use `scout-260117-ui-quick-reference.md` "Critical Signal Paths" section

**I want to modify the color scheme:**
→ See color constants in each file or search for hex color values

---

## Statistics

| Metric | Value |
|--------|-------|
| Total Files | 12 |
| Total Lines | 10,313 |
| Main Classes | 35+ |
| PyQt5 Widgets | 40+ |
| Custom Widgets | 8 |
| Signal Types | 30+ |
| Largest File | main_window.py (2,828 lines) |
| Smallest File | __init__.py (1 line) |
| Average File Size | 859 lines |

---

## Technical Highlights

### Sophisticated Zone Management
- 8 resize handles (4 corners + 4 edges)
- Boundary constraints within image
- Z-order management for overlapping zones
- Context menu support
- Multi-zone type support (removal/protection)

### Advanced Graphics System
- Dual synchronized preview panels
- Real-time zone overlay visualization
- Custom drawing mode with keyboard shortcuts
- Animated loading spinner with gradient
- QPainter-based custom icons

### Responsive Threading
- Single-file processing in background thread
- Batch processing with progress reporting
- Async YOLO detection without UI blocking
- Progress callbacks with page tracking
- Cancellation support

### Smart UI Organization
- Collapsible settings panel
- Compact toolbar for minimized mode
- Splitter-based layout (sidebar + content)
- Hover-based dropdown menus
- Persistent window state

---

## Next Steps

1. **Review** the quick reference guide for your specific task
2. **Navigate** to the detailed report for component deep-dive
3. **Examine** the actual source code with newfound context
4. **Trace** signal connections as needed
5. **Refer** back to these documents as you develop

---

Generated by **Codebase Scout** - Advanced code analysis for rapid understanding.

For questions or clarifications, refer to the detailed reports or examine the source code directly.
