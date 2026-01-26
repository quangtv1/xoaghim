# Xóa Vết Ghim PDF - Project Overview & PDR

## Project Summary

**Project Name:** Xóa Vết Ghim PDF (PDF Staple Mark Remover)
**Version:** 1.1.22
**Organization:** HUCE
**Framework:** PyQt5 (Python 3.8+)
**Platform:** Windows, macOS, Linux
**Repository:** [GitHub](https://github.com/quangtv1/xoaghim)

A professional desktop application using AI-powered layout detection to intelligently remove staple marks and artifacts from scanned PDF documents while preserving content integrity.

## Product Development Requirements (PDR)

### Functional Requirements

#### F1. File Management
- **F1.1** Support single file and batch folder processing
- **F1.2** Drag & drop file handling (macOS/Windows support)
- **F1.3** Sidebar file filters (by name and page count in batch mode)
- **F1.4** Loading overlay with spinner for large PDFs (>20 pages)
- **F1.5** Auto-recovery of files, folders, and zone selections on crash
- **F1.6** DPI adjustment (72-300) with optional JPEG compression

#### F2. Zone Selection & Management
- **F2.1** 8 preset zones: 4 corners (TL, TR, BL, BR) + 4 edges (top, bottom, left, right)
- **F2.2** Custom draw mode for arbitrary zone shapes (Cmd+A / Alt+A to activate)
- **F2.3** Hybrid zone sizing: fixed pixels for corners, percentage for edges
- **F2.4** Global zones (apply to all files) and per-file zones
- **F2.5** Per-page zone filtering (all, odd, even, current page)
- **F2.6** Undo/Redo with up to 79 action history (Ctrl+Z / Cmd+Z)
- **F2.7** Delete zones via Delete key or UI controls
- **F2.8** Zone counter display on bottom status bar (global + per-file counts)
- **F2.9** Persistent zone configuration across application restarts
- **F2.10** Select Mode toggle (Cmd+S / Alt+S) for zone selection

#### F3. Content Protection
- **F3.1** Automatic color preservation for red/blue signatures and marks
- **F3.2** AI-powered layout detection using YOLO DocLayNet (ONNX Runtime)
- **F3.3** Automatic detection of text regions, tables, figures, captions
- **F3.4** Exclusion of protected regions from staple removal processing
- **F3.5** Optional toggle for text protection (enable/disable per batch)
- **F3.6** Sensitivity adjustment slider for artifact detection

#### F4. Preview & Visualization
- **F4.1** Synchronized split-view preview (original | processed)
- **F4.2** Real-time preview updates as zones are modified
- **F4.3** Synchronized scrolling between left and right panels
- **F4.4** Synchronized zoom between panels
- **F4.5** Zoom preservation in batch mode (maintains zoom when switching files)
- **F4.6** Multi-page continuous preview with draggable/resizable zone overlays
- **F4.7** Visual zone item rendering with selection feedback

#### F5. Output & Export
- **F5.1** Batch processing with multiple file output
- **F5.2** Smart PDF compression options
- **F5.3** Configurable output directory
- **F5.4** Progress indication during export
- **F5.5** Support for single-page and multi-page PDF output modes

### Non-Functional Requirements

#### N1. Performance
- **N1.1** Large PDF handling (>100 pages) with progressive loading
- **N1.2** Real-time zone manipulation without lag
- **N1.3** <500ms response time for zone selection/modification
- **N1.4** Memory-efficient image caching with smart purging
- **N1.5** ONNX inference optimization with hardware acceleration support

#### N2. Reliability
- **N2.1** Automatic crash recovery with state persistence
- **N2.2** Graceful error handling for corrupted PDFs
- **N2.3** Validation of user inputs before processing
- **N2.4** Comprehensive exception logging

#### N3. Maintainability
- **N3.1** Modular architecture with clear separation of concerns
- **N3.2** Signal/slot pattern for UI-core communication
- **N3.3** Comprehensive unit test coverage (108 tests, 98%+ pass rate)
- **N3.4** Type hints throughout codebase
- **N3.5** Consistent code formatting and naming conventions

#### N4. Usability
- **N4.1** Intuitive UI following modern design principles (minimal gray theme)
- **N4.2** Keyboard shortcuts (Ctrl+Z/Cmd+Z undo, Cmd+A/Alt+A draw, Cmd+S/Alt+S select, +/- zoom)
- **N4.3** Contextual help and tooltips
- **N4.4** Multi-language support (Vietnamese/English)

#### N5. Security
- **N5.1** No external API calls for processing (all local)
- **N5.2** Safe file handling with permission checks
- **N5.3** Input validation for all user-provided paths and parameters
- **N5.4** Secure temporary file cleanup

### Technical Constraints

#### T1. Dependencies
- **T1.1** PyQt5 5.15+ for UI framework
- **T1.2** OpenCV 4.5+ for image processing
- **T1.3** Pillow 8.0+ for image format handling
- **T1.4** PyMuPDF or pypdf for PDF manipulation
- **T1.5** ONNX Runtime 1.11+ for ML inference
- **T1.6** NumPy for numerical operations

#### T2. Architecture
- **T2.1** PyQt5 threading model (QThread for background tasks)
- **T2.2** Model-View-Controller (MVC) separation
- **T2.3** Signal/Slot pattern for inter-component communication
- **T2.4** Configuration persistence via QSettings

#### T3. Compatibility
- **T3.1** Windows 10+ (x64)
- **T3.2** macOS 10.14+ (Intel & Apple Silicon via universal binary)
- **T3.3** Linux CentOS 7+ / Rocky / RHEL
- **T3.4** Python 3.8, 3.9, 3.10, 3.11, 3.12

## Acceptance Criteria

### For Zone Management Feature
- [ ] All 8 preset zones display correctly on preview
- [ ] Custom draw mode creates arbitrary polygon zones
- [ ] Hybrid sizing works for corner (fixed pixels) and edge (percentage) zones
- [ ] Undo history maintains up to 79 actions without memory leaks
- [ ] Zone configuration persists across application restarts

### For Batch Processing
- [ ] Sidebar filters correctly by filename and page count
- [ ] Loading overlay displays for PDFs >20 pages
- [ ] Processing completes without data loss
- [ ] Output files match processing parameters

### For Content Protection
- [ ] AI detection correctly identifies text, tables, figures, captions
- [ ] Red/blue signature colors are preserved
- [ ] Protected regions are excluded from artifact removal
- [ ] Performance degradation <15% with text protection enabled

### For UI/UX
- [ ] All elements render correctly at 100%, 125%, 150%, 200% DPI scaling
- [ ] Drag & drop works on target platforms
- [ ] Keyboard navigation fully functional
- [ ] Responsive layout adapts to window resizing

## Success Metrics

### User Experience
- **Metric 1:** Time to process single file: <2s for 10-page document
- **Metric 2:** Zone creation/modification response: <200ms
- **Metric 3:** User satisfaction on ease of zone selection: >4.0/5.0
- **Metric 4:** Staple mark removal accuracy: >95% without content damage

### System Performance
- **Metric 5:** Memory usage for 100-page PDF: <500MB
- **Metric 6:** CPU utilization during preview: <30% (single core)
- **Metric 7:** Batch processing throughput: 3-5 pages/second

### Code Quality
- **Metric 8:** Test coverage: >85% for core modules
- **Metric 9:** Code duplication: <5%
- **Metric 10:** Average cyclomatic complexity per function: <8

## Version History

### v1.1.22 (Current)
- Fixed "Xóa tất cả" not persisting to JSON in single/batch mode
- Improved protected region caching from preview to Clean with DPI scaling
- Fixed kernel size scaling in zone processing
- Fixed text protection consistency in process operations
- Added memory cleanup when loading new file/folder

### v1.1.21
- Added sidebar file filters (name + pages)
- Loading overlay for large PDFs
- Zone counter on status bar
- Delete zones globally/per-file/per-page
- Auto-recovery on crash
- Undo (Ctrl+Z) support
- Delete key for zone removal
- Hybrid zone sizing
- Batch mode zoom preservation

### v1.1.18-v1.1.20
- Compact settings toolbar (collapsed mode)
- Zone persistence across restarts
- Batch preview container
- Text protection AI integration

### v1.0.0
- Core staple removal engine
- Basic UI with preview
- Zone management (preset + custom)
- PDF I/O and export

## Development Roadmap

### Next Releases (v1.2.x)
- [ ] UI/UX refinements based on user feedback
- [ ] Performance optimization for >500 page documents
- [ ] Additional ML models (document rotation, quality assessment)
- [ ] Batch export with detailed progress reporting
- [ ] Plugin architecture for custom processors

### Future Considerations (v2.0)
- [ ] Web-based interface
- [ ] API server for integration
- [ ] Cloud processing option
- [ ] Multi-threaded batch processing
- [ ] Advanced document analysis tools

## Dependencies & Integrations

### External Libraries
- **PyQt5:** UI framework and event handling
- **OpenCV (cv2):** Image processing and artifact detection
- **Pillow:** Image format conversion and optimization
- **ONNX Runtime:** ML model inference for layout detection
- **PyMuPDF/pypdf:** PDF reading and manipulation
- **NumPy:** Array operations for image processing

### Configuration Storage
- **QSettings:** Cross-platform application settings
- **File-based:** Zone configurations stored in JSON format

## Team & Responsibilities

- **Developer:** Quang TV
- **Organization:** HUCE
- **Support:** GitHub Issues

## Document Control

- **Last Updated:** 2026-01-26
- **Version:** 1.2
- **Status:** Current (v1.1.22)
- **Generated by:** Documentation manager
