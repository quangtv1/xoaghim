# XoaGhim PDF - Project Roadmap

**Last Updated:** 2026-01-26
**Current Version:** 1.1.22

---

## Release Timeline

### v1.1.22 (Current - Stable)

**Status:** All Bug Fixes & Features Complete
- Fixed "Xóa tất cả" not persisting to JSON in single/batch mode
- Improved protected region caching from preview with DPI scaling
- Fixed kernel size scaling in zone processing
- Fixed text protection consistency across operations
- Enhanced memory cleanup when loading new files/folders

**Release Date:** 2026-01-26
**Status:** Stable/Production

**Cumulative v1.1.x Features:**
- Sidebar file filters (name + page count)
- Loading overlay for large PDFs (>20 pages)
- Zone counter on status bar (global + per-file + per-page)
- Delete zones (global/per-file/per-page)
- Auto-recovery on crash
- Undo (Ctrl+Z/Cmd+Z) up to 79 actions
- Delete key for zone removal
- Hybrid zone sizing (pixels + percentage)
- Batch mode zoom preservation
- Compact settings toolbar
- AI text protection with YOLO DocLayNet
- Draw Mode (Cmd+A/Alt+A) and Select Mode (Cmd+S/Alt+S) shortcuts
- Zoom controls (+, -, =)

---

### Q1 2026 (Late January - March)

#### v1.2.0 - GPU Acceleration & Performance

**Major Features:**
- [ ] CUDA support for ONNX Runtime (GPU detection)
- [ ] Automatic GPU detection and fallback
- [ ] Performance profiling dashboard
- [ ] Memory usage monitoring
- [ ] Batch processing parallelization (configurable workers)

**Performance Targets:**
- Single page: <2 sec (vs 5 sec current)
- AI detection: <1 sec on GPU (vs 3-5 sec current)
- Memory optimization: 30% reduction

**Breaking Changes:** None

**Testing:**
- GPU hardware testing (NVIDIA)
- Fallback behavior on CPU-only systems
- Performance regression tests

#### v1.1.19 - Bug Fixes & Stability

**Bug Fixes:**
- [ ] High DPI display rendering issues
- [ ] Memory leak in batch processing
- [ ] Config file corruption recovery
- [ ] Windows drag & drop edge cases
- [ ] Long filename handling

**QA Focus:**
- Stability on large PDFs (1000+ pages)
- Cross-platform config compatibility
- Thread safety under load

---

### Q2 2026 (April - June)

#### v1.3.0 - Advanced Zone Features

**Major Features:**
- [ ] User-defined zone profiles (save/load templates)
- [ ] Zone presets for common document types (invoice, contract, book page)
- [ ] Undo/Redo for zone modifications
- [ ] Zone history with snapshots
- [ ] Batch zone templates (apply to all files)
- [ ] Smart zone detection (auto-detect common staple locations)

**Usability Improvements:**
- Preset templates dropdown
- Quick-access zone history
- Visual zone preview before processing
- Zone optimization suggestions

**UI Changes:**
- New "Zone Profiles" panel
- Profile manager dialog
- Zone history dropdown

#### v1.2.1 - Minor Updates

**Small Enhancements:**
- [ ] Dark mode UI theme
- [ ] Keyboard shortcut customization
- [ ] Recent files menu
- [ ] Batch export log export
- [ ] Configuration export/import

---

### Q3 2026 (July - September)

#### v1.4.0 - Web Interface & Server Deployment

**Major Features:**
- [ ] RESTful API for core processing
- [ ] Web UI (React/Vue frontend)
- [ ] Multi-user support with authentication
- [ ] Job queue and scheduling
- [ ] Results storage and retrieval
- [ ] Admin dashboard

**Architecture:**
- Backend: Python FastAPI/Flask
- Database: SQLite or PostgreSQL
- Frontend: React with TypeScript
- Deployment: Docker containers

**Integration:**
- Existing core modules reusable
- New API layer wrapping processors
- Separate web service deployment

**Security:**
- User authentication (OAuth2)
- Rate limiting
- File upload validation
- Processing isolation

#### v1.3.1 - Stability & Polish

**Focus:**
- Bug fixes from v1.3.0
- Performance tuning
- Documentation updates
- Community feedback integration

---

### Q4 2026 (October - December)

#### v1.5.0 - Enterprise Features

**Major Features:**
- [ ] Advanced OCR integration (text extraction)
- [ ] Document classification (detect document type)
- [ ] Audit logging and compliance
- [ ] LDAP/Active Directory integration
- [ ] Volume licensing

**OCR Integration:**
- Extract text from documents
- Automatic language detection
- Searchable PDF output
- Text-based zone protection (don't touch text areas)

**Compliance:**
- Audit trail of all operations
- Data retention policies
- Encryption at rest
- GDPR compliance features

#### v1.4.1 - Server Hardening

**Focus:**
- Security testing
- Performance optimization
- Load testing (concurrent users)
- Monitoring and alerts

---

## Feature Backlog (Future, No Specific Timeline)

### High Priority

- [ ] Advanced filters (noise reduction, deskew, despeckle)
- [ ] Batch job scheduling (schedule processing at off-peak)
- [ ] Integration with document management systems (SharePoint, Alfresco)
- [ ] Mobile app (React Native) for preview and configuration
- [ ] Machine learning for zone auto-detection per document
- [ ] Multi-page zone patterns (detect repeating patterns)

### Medium Priority

- [ ] Support for other document formats (TIFF, EPS, JPG)
- [ ] Batch preview thumbnails
- [ ] PDF annotation support (preserve/remove)
- [ ] Advanced compression settings
- [ ] Document watermarking
- [ ] Blurring/redaction tools
- [ ] Comparison view (before/after slider)

### Low Priority

- [ ] Theme customization
- [ ] Plugin API for custom processors
- [ ] Command-line batch processing
- [ ] Linux native package (snap, flatpak)
- [ ] Installer for Windows (NSIS/MSI)
- [ ] macOS DMG installer
- [ ] Localization (Vietnamese, French, Spanish, etc.)

---

## Known Limitations & Future Solutions

### Current Limitations

| Limitation | Impact | Solution (Future) |
|-----------|--------|------------------|
| ONNX model ~100MB | First-time setup delay | Compression, streaming download |
| CPU-only AI | Slow processing (3-5s per page) | GPU acceleration (v1.2) |
| Single user | Not for shared teams | Web interface (v1.4) |
| No OCR | Text extraction limited | OCR integration (v1.5) |
| No zone profiles | Repetitive setup | Zone templates (v1.3) |
| No web interface | Team collaboration limited | Web UI (v1.4) |
| Batch throughput | ~3-5 pages/sec | GPU acceleration (v1.2) |

---

## Technical Debt

### Items to Address

**Code Quality:**
- [ ] Increase test coverage from 80% to 90%+ (core modules)
- [ ] Refactor large files (layout_detector.py > 1600 lines)
- [ ] Standardize error handling across modules
- [ ] Add type hints to UI modules
- [ ] Document complex algorithms

**Performance:**
- [ ] Profile memory usage in batch mode
- [ ] Optimize image processing (vectorize more operations)
- [ ] Cache model inference results
- [ ] Implement progressive loading for preview

**Maintainability:**
- [ ] Add integration tests for workflows
- [ ] Create e2e test suite (selenium-like)
- [ ] Document architecture decisions (ADRs)
- [ ] Setup continuous integration/deployment
- [ ] Create developer guide

**Dependencies:**
- [ ] Evaluate alternatives to large deps (ONNX Runtime)
- [ ] Pin exact versions in CI/CD
- [ ] Test against new versions regularly
- [ ] Create dependency update policy

---

## Release Strategy

### Version Numbering

**Format:** MAJOR.MINOR.PATCH
- MAJOR: Breaking changes or major feature releases
- MINOR: New features, non-breaking
- PATCH: Bug fixes, small improvements

**Example:**
- v1.0.0: First stable release
- v1.1.18: Current (bug fixes + compact toolbar)
- v2.0.0: Major refactor or breaking API change

### Release Cadence

**Stable Releases:**
- Major/Minor: Quarterly (every 3 months)
- Patches: As needed (1-2 weeks after issues found)

**Pre-releases:**
- Alpha: Feature complete, testing phase
- Beta: Release candidate, community testing
- RC: Ready for production

### Release Checklist

Before each release:
- [ ] All tests pass (unit + integration)
- [ ] Code review completed
- [ ] Changelog updated
- [ ] Documentation updated
- [ ] Performance regression tests pass
- [ ] Security audit completed
- [ ] Build artifacts generated (Windows ZIP)
- [ ] Release notes written
- [ ] GitHub release created
- [ ] Announcement posted

---

## Milestones

### 2026 Goals

**Q1:**
- [ ] v1.2.0 GPU acceleration
- [ ] Performance improvements (2-3x faster)
- [ ] Stability hardening

**Q2:**
- [ ] v1.3.0 Zone profiles
- [ ] Advanced features
- [ ] UI polish

**Q3:**
- [ ] v1.4.0 Web interface
- [ ] Server deployment option
- [ ] Multi-user support

**Q4:**
- [ ] v1.5.0 Enterprise features
- [ ] OCR integration
- [ ] Production hardening

### 2027 Vision

**Goals:**
- Enterprise adoption
- Server deployment in organizations
- Web interface widely used
- Community plugins/extensions
- Advanced document processing capabilities

**Investment Areas:**
- Scale testing (1000+ concurrent users)
- Cloud deployment (AWS/Azure/GCP)
- Compliance certifications
- Support and documentation

---

## Community & Feedback

### Getting User Input

**Channels:**
- GitHub Issues for bug reports
- GitHub Discussions for feature requests
- User surveys (quarterly)
- Beta testing program

**Features by Request:**
- Track community votes on features
- Prioritize high-demand items
- Publish rationale for decisions

### Contributing

**Open Source:**
- [ ] Set up development guidelines
- [ ] Create contributor code of conduct
- [ ] Document contribution process
- [ ] Review external PRs
- [ ] Maintain contributor list

---

## Risk Assessment

### Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| ONNX model incompatibility | Can't use AI | Low | Version pinning, fallback |
| GPU memory limits | Processing fails | Medium | Streaming inference |
| PDF corruption on export | Data loss | Low | Validation, backups |
| Performance regression | User experience | Medium | Automated benchmarks |
| Dependency conflicts | Build failures | Medium | CI/CD, version bounds |

### Market Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| Declining interest | Development stops | Low | Show use cases, marketing |
| Competitor tool | Market share loss | Medium | Differentiate features |
| Budget constraints | Slower development | Medium | Open source contributions |
| Key person departure | Knowledge loss | Low | Documentation, team |

---

## Resource Planning

### Current Team

**Estimated:**
- Lead Developer: 1 FTE
- QA/Testing: 0.5 FTE
- Documentation: 0.25 FTE

**Total:** ~1.75 FTE

### Q1-Q2 2026 Needed

**For GPU & Features:**
- Software Engineer (GPU optimization): 1 FTE
- QA Engineer: 0.5 FTE
- Product Manager: 0.25 FTE

**Total:** ~2.5 FTE

### Q3+ 2026 Needed (Web Interface)

**For Web Platform:**
- Backend Engineer (API): 1 FTE
- Frontend Engineer (React): 1 FTE
- DevOps Engineer (Infrastructure): 0.5 FTE
- QA Engineer: 1 FTE
- Product Manager: 0.5 FTE

**Total:** ~4 FTE

---

## Success Metrics

### Adoption

| Metric | 2026 Target | 2027 Target |
|--------|-----------|-----------|
| GitHub stars | 100+ | 500+ |
| Monthly downloads | 1,000+ | 10,000+ |
| Active users | 50+ | 500+ |
| Enterprise customers | 0 | 5+ |

### Quality

| Metric | Target |
|--------|--------|
| Test coverage | 80%+ |
| Uptime (web) | 99.5%+ |
| Response time (API) | <500ms |
| Bug fix time | <1 week |

### Performance

| Metric | Target | Current |
|--------|--------|---------|
| Page process time | <2 sec | 5 sec |
| AI detect time | <1 sec GPU | 3-5 sec |
| Batch throughput | 1000 pages/hour | 200-300 |
| Memory footprint | 300 MB | 400+ MB |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.2 | 2026-01-26 | Docs Manager | Updated for v1.1.22 release (bug fixes + stability) |
| 1.1 | 2026-01-19 | Docs Manager | Updated for v1.1.21 release (all core features complete) |
| 1.0 | 2026-01-17 | Team | Initial roadmap (v1.1.18 baseline) |

