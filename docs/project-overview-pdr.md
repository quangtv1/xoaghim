# XoaGhim PDF - Project Overview & PDR

**Project Name:** Xóa Vết Ghim PDF (Remove Staple Marks PDF)
**Version:** 1.1.18
**Organization:** HUCE
**Last Updated:** 2026-01-17
**Status:** Active Development

---

## Executive Summary

XoaGhim is a desktop application that removes staple marks and damage from scanned PDF documents using advanced image processing and AI-powered layout detection. Built with PyQt5 and Python, it provides both single-file and batch processing capabilities with real-time preview and configurable protection zones.

**Target Users:** Document management teams, archivists, administrative staff processing scanned PDFs

**Key Value Proposition:** Automate staple mark removal while intelligently protecting important document content (text, signatures, tables)

---

## Product Development Requirements (PDR)

### 1. Functional Requirements

#### 1.1 File Processing
- **FR1.1** Support single PDF file processing via file dialog
- **FR1.2** Support batch processing of multiple PDFs from directory
- **FR1.3** Implement drag & drop file input for Windows and macOS
- **FR1.4** Display file metadata: filename, page count, file size
- **FR1.5** Implement page filtering: all pages / odd pages only / even pages only / current page

#### 1.2 Zone Selection & Configuration
- **FR2.1** Provide 8 preset zones: 4 corners (top-left, top-right, bottom-left, bottom-right) + 4 edges (top, bottom, left, right)
- **FR2.2** Implement custom zone drawing mode for flexible region definition
- **FR2.3** Support multi-page zone application (apply same zone to multiple pages)
- **FR2.4** Persist zone configuration to disk (JSON) across app sessions
- **FR2.5** Provide zone reset options: manual zones only / auto-detected zones / all zones
- **FR2.6** Display visual zone representation on paper icon
- **FR2.7** Support draggable zone boundaries with 8 resize handles

#### 1.3 Content Protection
- **FR3.1** Automatically detect and protect red/blue colored pixels (signatures, marks)
- **FR3.2** Implement AI-powered layout detection using YOLO DocLayNet (ONNX)
- **FR3.3** Support 11 layout categories: text, title, list, table, figure, caption, header, footer, page-number, footnote, section-header
- **FR3.4** Exclude detected protected regions from staple removal processing
- **FR3.5** Allow toggle of AI protection on/off

#### 1.4 Preview & Visualization
- **FR4.1** Implement side-by-side preview: original | processed (synchronized)
- **FR4.2** Support synchronized zoom and scroll between preview panels
- **FR4.3** Implement continuous (multi-page) and single-page preview modes
- **FR4.4** Display zones as overlay on preview with visual handles
- **FR4.5** Real-time preview update as zone/threshold settings change

#### 1.5 Output & Export
- **FR5.1** Export processed PDF with configurable DPI (72-300)
- **FR5.2** Implement JPEG compression for color pages, TIFF for B/W
- **FR5.3** Support output file naming: original name + "_clean" suffix
- **FR5.4** Allow custom output directory selection
- **FR5.5** Display export progress for batch operations

#### 1.6 User Interface
- **FR6.1** Implement menu bar with File, Edit, View, Help menus
- **FR6.2** Provide collapsible/expandable settings panel with detail and compact modes
- **FR6.3** Display bottom status bar with page info and zoom controls
- **FR6.4** Support keyboard shortcuts: Ctrl+O (open), Ctrl+Enter (run), Ctrl+/- (zoom)
- **FR6.5** Implement compact icon-only toolbar for collapsed settings panel
- **FR6.6** Auto-save window size and sidebar width on close

### 2. Non-Functional Requirements

#### 2.1 Performance
- **NFR1.1** Page caching: maintain 10 pages in memory for quick navigation
- **NFR1.2** AI inference latency: <5 seconds per page (on CPU)
- **NFR1.3** Preview rendering: <500ms per page update
- **NFR1.4** Batch processing: handle 100+ files without memory leaks
- **NFR1.5** Support PDFs up to 1000+ pages efficiently

#### 2.2 Compatibility
- **NFR2.1** Python 3.8+ support
- **NFR2.2** Cross-platform: Windows, macOS, Linux
- **NFR2.3** Windows high-DPI display support
- **NFR2.4** Bundled ONNX Runtime and VC++ Runtime DLLs for Windows

#### 2.3 Reliability
- **NFR3.1** Handle corrupted PDF gracefully with error messages
- **NFR3.2** Validate zone coordinates before processing
- **NFR3.3** Implement background processing threads to prevent UI freezing
- **NFR3.4** Maintain configuration backups automatically

#### 2.4 Security
- **NFR4.1** No external network calls (all processing local)
- **NFR4.2** Preserve original PDFs (always create new output)
- **NFR4.3** No sensitive data logging

#### 2.5 Maintainability
- **NFR5.1** Modular architecture: core processing separated from UI
- **NFR5.2** Comprehensive test coverage (6 test files, 124+ test cases)
- **NFR5.3** Configuration in JSON for easy user customization
- **NFR5.4** Clear class separation: Zone dataclass, StapleRemover, PDFHandler, LayoutDetector

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────┐
│   Presentation Layer (PyQt5 UI)     │
│  main_window.py, settings_panel.py  │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│   Application Layer                 │
│  continuous_preview.py, zone_item.py│
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│   Business Logic Layer (core/)      │
│  processor, layout_detector,        │
│  zone_optimizer, pdf_handler        │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│   Data Layer                        │
│  config_manager, PDF files          │
└─────────────────────────────────────┘
```

### Core Components

**Processor Module** (670 lines)
- Zone dataclass: coordinates (%), threshold, enabled flag
- StapleRemover class: background color detection, red/blue pixel protection
- 8 PRESET_ZONES for corners and edges

**PDF Handler Module** (645 lines)
- PDFHandler: page rendering with caching
- PDFExporter: compression with format selection (JPEG/TIFF)
- Lazy loading for memory efficiency

**Layout Detector Module** (1,602 lines)
- 6 backend support: YOLO DocLayNet (primary), PyTorch, PaddleOCR, legacy, Detectron2, GPU server
- ProtectedRegion dataclass with 11 categories
- Lazy model loading for first-use optimization

**Zone Optimizer Module** (315 lines)
- Shapely-based polygon safe zone calculation
- Text protection integration

**Config Manager Module** (124 lines)
- Platform-specific paths: ~/Library (macOS), %APPDATA% (Windows), ~/.config (Linux)
- JSON persistence for zones, thresholds, settings

---

## Feature Breakdown

### v1.1.18 (Current)
- Compact toolbar with icon-only settings (detail/compact toggle)
- 8 zone toggle buttons + draw mode buttons
- Page filter buttons (all/odd/even/current)
- Enhanced toolbar state synchronization
- Window size & sidebar width auto-save

### v1.1.17
- Zone config persistence (JSON)
- 2-click zone reset
- Auto-save on app close

### v1.1.16
- Custom zone draw mode
- AI layout detection (ONNX)
- Multi-page zone selection
- 3-option reset popup

### v1.1.15 and Earlier
- Preset zones (8)
- Batch processing
- Drag & drop support
- Red/blue pixel protection
- Synchronized dual preview

---

## Technical Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.8+ |
| GUI | PyQt5 | ≥5.15.0 |
| PDF Processing | PyMuPDF (fitz) | ≥1.20.0 |
| Image Processing | OpenCV | ≥4.5.0 |
| AI Inference | ONNX Runtime | ≥1.22.0 |
| Geometry | Shapely | ≥2.0.0 |
| Arrays | NumPy | ≥1.20.0 |
| Testing | unittest/pytest | - |

### Optional Dependencies
- ultralytics (YOLO training)
- torch (PyTorch backend)
- PaddleOCR (alternative layout detection)
- detectron2 (Detectron2 backend)

---

## Success Metrics & KPIs

### Functional Metrics
- **FR Coverage:** 100% of required features implemented
- **Test Coverage:** ≥80% of core modules
- **Platform Support:** Passes on Windows, macOS, Linux

### Performance Metrics
- **Processing Speed:** <5 sec/page on CPU
- **Memory Usage:** <500MB for 100-page document
- **UI Responsiveness:** <200ms max freeze time

### Reliability Metrics
- **Error Handling:** 0 uncaught exceptions on invalid input
- **Configuration Persistence:** 100% recovery on app restart
- **Batch Success Rate:** ≥99% of files processed without crash

### User Satisfaction
- **Setup Time:** <5 minutes from download to first use
- **Learning Curve:** First document processed in <10 minutes
- **User Retention:** Track version adoption

---

## Acceptance Criteria

### Acceptance for v1.1.18
- [ ] Compact toolbar displays correctly in collapsed mode
- [ ] All 8 zone buttons toggle zones independently
- [ ] Draw mode buttons (add/remove) are mutually exclusive
- [ ] Filter buttons (all/odd/even/current) are mutually exclusive
- [ ] Clear zones button empties all zones
- [ ] AI detect button triggers layout detection
- [ ] Toolbar state syncs with settings panel in real-time
- [ ] Window size saved and restored on restart
- [ ] Sidebar width saved and restored on restart
- [ ] All 124 tests pass
- [ ] No regressions on v1.1.17 features

### General Acceptance
- [ ] Single file processing: select → zone → run → export
- [ ] Batch processing: select folder → zone → run → export all
- [ ] Preview renders correctly at all zoom levels
- [ ] Zone overlay updates in real-time
- [ ] AI protection mode works (red/blue + layout detection)
- [ ] Output PDFs match quality expectations
- [ ] Cross-platform builds succeed (Windows/macOS)
- [ ] No file corruption on any supported PDF type

---

## Known Limitations & Future Considerations

### Current Limitations
1. ONNX layout detection requires CPU download on first use (~100MB)
2. AI detection slower on older hardware (<2GHz CPU)
3. Very large PDFs (1000+ pages) may require multiple sessions
4. Custom zones not automatically exported to other users

### Future Enhancements
1. GPU acceleration for layout detection
2. Batch zone templates for common document types
3. User-defined zone profiles (save/load)
4. Server-side GPU processing option
5. Web UI for remote processing
6. Advanced OCR for text extraction/protection
7. Undo/redo for zone modifications
8. Advanced filters (noise reduction, deskew)

---

## Dependencies & Deployment

### Build & Release
- GitHub Actions workflow: `.github/workflows/build-windows.yml`
- PyInstaller: onedir mode for Windows
- Bundled: ONNX Runtime DLLs, VC++ Runtime DLLs
- Output: `XoaGhim-{version}-Windows.zip`

### Installation Methods
1. **Source:** Clone + `pip install -r requirements.txt`
2. **Windows Build:** Download ZIP from releases
3. **Future:** Conda package, installer

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| ONNX model download failure | Medium | Fallback to PyTorch backend or disable AI |
| PDF corruption during export | High | Test with diverse PDF types, validate output |
| Performance on large files | Medium | Implement streaming, page caching |
| Cross-platform UI inconsistency | Low | Test on all platforms, PyQt5 handles most |
| Zone config file corruption | Low | Auto-backup, validation on load |

---

## Roadmap & Timeline

### Q1 2026 (In Progress)
- Compact toolbar refinement
- GPU acceleration exploration
- Performance benchmarking

### Q2 2026 (Planned)
- Advanced zone templates
- User-defined zone profiles
- Web preview integration

### Q3 2026 (Future)
- Server-side GPU processing
- Batch job scheduling
- Advanced OCR features

---

## Revision History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-17 | Initial PDR document |

