/**
 * 面板样式。全部挂在 `.dsd-app` 作用域下，避免污染 shell 自身样式。
 */

export const APP_CSS = `
.dsd-app {
  --dsd-bg: #f5f8fd;
  --dsd-surface: #ffffff;
  --dsd-ink: #1b2a41;
  --dsd-muted: #6b7a90;
  --dsd-line: #dde5f0;
  --dsd-accent: #2563eb;
  --dsd-accent-soft: #e9f0ff;
  --dsd-teal: #0d9488;
  --dsd-warn: #b45309;
  --dsd-danger: #b42318;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  width: 100%;
  overflow: hidden;
  background: var(--dsd-bg);
  color: var(--dsd-ink);
  font-family: -apple-system, "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  font-size: 13px;
  line-height: 1.55;
}

/* ---------- banner ---------- */
.dsd-banner {
  position: relative;
  display: flex;
  align-items: center;
  gap: 22px;
  flex: 0 0 72px;
  padding: 0 22px;
  border-bottom: 1px solid var(--dsd-line);
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(8px);
  overflow: hidden;
  z-index: 2;
}
.dsd-banner::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(90deg, rgba(37, 99, 235, 0.05) 1px, transparent 1px),
    linear-gradient(rgba(37, 99, 235, 0.05) 1px, transparent 1px);
  background-size: 26px 26px;
  mask-image: linear-gradient(90deg, transparent 35%, #000 80%);
  -webkit-mask-image: linear-gradient(90deg, transparent 35%, #000 80%);
  pointer-events: none;
}
.dsd-banner > * { position: relative; }
.dsd-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  flex: 0 0 auto;
}
.dsd-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  color: var(--dsd-accent);
  background: linear-gradient(145deg, #eef4ff, #dbeafe);
  border: 1px solid #c7dbfb;
}
.dsd-brand-name { font-size: 14px; font-weight: 650; letter-spacing: 0.01em; }
.dsd-brand-en {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--dsd-muted);
  margin-top: -2px;
}
.dsd-crumbs {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 12px;
  color: var(--dsd-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dsd-crumb-sep { color: #b9c5d6; }
.dsd-crumb-current { color: var(--dsd-ink); font-weight: 600; }
.dsd-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08);
}

/* ---------- body ---------- */
.dsd-body {
  display: flex;
  flex: 1 1 auto;
  min-height: 0;
}
.dsd-sidebar {
  display: flex;
  flex-direction: column;
  flex: 0 0 224px;
  width: 224px;
  border-right: 1px solid var(--dsd-line);
  background: rgba(255, 255, 255, 0.72);
  transition: width 0.18s ease, flex-basis 0.18s ease;
  overflow: hidden;
}
.dsd-sidebar.is-collapsed {
  flex-basis: 56px;
  width: 56px;
}
.dsd-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: 0 0 46px;
  padding: 0 10px 0 16px;
}
.dsd-sidebar-title {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--dsd-muted);
  white-space: nowrap;
}
.dsd-collapse {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--dsd-muted);
  cursor: pointer;
}
.dsd-collapse:hover { background: var(--dsd-accent-soft); color: var(--dsd-accent); }
.dsd-menu {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 4px 8px 12px;
  overflow-y: auto;
  min-height: 0;
}
.dsd-menu-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 8px 10px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--dsd-ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.dsd-menu-item:hover { background: rgba(37, 99, 235, 0.06); }
.dsd-menu-item.is-active {
  background: var(--dsd-accent-soft);
  color: var(--dsd-accent);
  font-weight: 600;
}
.dsd-menu-item .dsd-menu-icon { flex: 0 0 auto; opacity: 0.9; }
.dsd-menu-label { flex: 1 1 auto; min-width: 0; }
.dsd-menu-parent .dsd-chevron { margin-left: auto; color: var(--dsd-muted); }
.dsd-menu-sub {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 2px 0 4px 17px;
  padding-left: 8px;
  border-left: 1px dashed #ccd7e6;
}
.dsd-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
}
.dsd-rail-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: var(--dsd-muted);
  cursor: pointer;
}
.dsd-rail-button:hover { background: rgba(37, 99, 235, 0.06); color: var(--dsd-accent); }
.dsd-rail-button.is-active { background: var(--dsd-accent-soft); color: var(--dsd-accent); }

/* ---------- main ---------- */
.dsd-main {
  position: relative;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 30px 34px 44px;
}
.dsd-main::before {
  content: "";
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(90deg, rgba(37, 99, 235, 0.035) 1px, transparent 1px),
    linear-gradient(rgba(37, 99, 235, 0.035) 1px, transparent 1px);
  background-size: 32px 32px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent 55%);
  -webkit-mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent 55%);
  pointer-events: none;
  z-index: 0;
}
.dsd-main > * { position: relative; z-index: 1; }
.dsd-page { max-width: 1040px; margin: 0 auto; }

/* ---------- home ---------- */
.dsd-hero {
  display: flex;
  align-items: stretch;
  gap: 24px;
  padding: 28px 30px;
  border: 1px solid var(--dsd-line);
  border-radius: 16px;
  background: linear-gradient(135deg, #ffffff 0%, #f3f8ff 62%, #eef7f6 100%);
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(27, 42, 65, 0.04);
}
.dsd-hero-copy { flex: 1 1 auto; min-width: 0; }
.dsd-eyebrow {
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--dsd-teal);
}
.dsd-hero h1 {
  margin: 8px 0 10px;
  font-size: 30px;
  line-height: 1.2;
  letter-spacing: -0.02em;
  font-weight: 650;
}
.dsd-hero p {
  margin: 0;
  max-width: 560px;
  color: #495a70;
  font-size: 13.5px;
}
.dsd-hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}
.dsd-pill {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid #cfe0fa;
  background: rgba(255, 255, 255, 0.72);
  color: #31537f;
  font-size: 11.5px;
}
.dsd-hero-art {
  flex: 0 0 240px;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
}
.dsd-features {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}
.dsd-feature {
  padding: 16px 18px;
  border: 1px solid var(--dsd-line);
  border-radius: 12px;
  background: var(--dsd-surface);
}
.dsd-feature-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
}
.dsd-feature-title .dsd-feature-icon { color: var(--dsd-accent); }
.dsd-feature-body {
  margin: 6px 0 0;
  color: var(--dsd-muted);
  font-size: 12.5px;
}

/* ---------- environment page ---------- */
.dsd-page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.dsd-page-head h2 {
  margin: 0;
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.01em;
}
.dsd-page-head .dsd-page-sub {
  margin: 5px 0 0;
  font-size: 12.5px;
  color: var(--dsd-muted);
}
.dsd-toolbar { display: flex; gap: 8px; flex: 0 0 auto; }
.dsd-button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 14px;
  border-radius: 9px;
  border: 1px solid var(--dsd-line);
  background: var(--dsd-surface);
  color: var(--dsd-ink);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  white-space: nowrap;
}
.dsd-button:hover { border-color: #c3d3e8; background: #f8fbff; }
.dsd-button.is-primary {
  border-color: var(--dsd-accent);
  background: var(--dsd-accent);
  color: #fff;
}
.dsd-button.is-primary:hover { background: #1d4ed8; }
.dsd-button:disabled { opacity: 0.55; cursor: not-allowed; }
.dsd-env-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.dsd-card {
  padding: 16px 18px;
  border: 1px solid var(--dsd-line);
  border-radius: 12px;
  background: var(--dsd-surface);
  min-width: 0;
}
.dsd-env-section { padding: 17px 20px 18px; }
.dsd-section-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.dsd-section-index {
  flex: 0 0 auto;
  margin-top: 1px;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
  color: var(--dsd-accent);
  letter-spacing: 0.08em;
}
.dsd-section-heading { flex: 1 1 auto; min-width: 0; }
.dsd-section-title { font-size: 14px; font-weight: 600; }
.dsd-section-sub { margin-top: 1px; font-size: 11.5px; color: var(--dsd-muted); }
.dsd-kv-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 24px;
  margin-top: 13px;
}
.dsd-kv-wide { grid-column: 1 / -1; }
.dsd-action-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
  padding-top: 13px;
  border-top: 1px dashed var(--dsd-line);
}
.dsd-action-hint { color: var(--dsd-muted); font-size: 11.5px; }
.dsd-packages { margin-top: 12px; }
.dsd-packages-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border: 0;
  background: transparent;
  color: var(--dsd-accent);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.dsd-packages-toggle:hover { text-decoration: underline; }
.dsd-package-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 22px;
  margin-top: 6px;
  max-height: 240px;
  overflow-y: auto;
  padding: 10px 12px;
  border: 1px solid var(--dsd-line);
  border-radius: 8px;
  background: #fbfdff;
}
.dsd-package-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  font-size: 11.5px;
}
.dsd-package-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #334155;
}
.dsd-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.dsd-card-label {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--dsd-muted);
}
.dsd-card-flag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--dsd-muted);
}
.dsd-card-flag.is-ok { color: #0f766e; }
.dsd-card-flag.is-bad { color: var(--dsd-warn); }
.dsd-kv {
  display: flex;
  flex-direction: column;
  gap: 7px;
  font-size: 12.5px;
}
.dsd-kv-row { display: flex; gap: 10px; }
.dsd-kv-key { flex: 0 0 64px; color: var(--dsd-muted); }
.dsd-kv-value {
  flex: 1 1 auto;
  min-width: 0;
  overflow-wrap: anywhere;
}
.dsd-mono { font-family: "Cascadia Mono", Consolas, monospace; font-size: 11.5px; }
.dsd-deps {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
}
.dsd-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 7px;
  border: 1px solid #bfe8dd;
  background: #f0fbf8;
  color: #0f766e;
  font-size: 11.5px;
}
.dsd-chip.is-missing {
  border-color: #f0d9b5;
  background: #fffaf1;
  color: var(--dsd-warn);
}
.dsd-chip-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}
.dsd-card-wide { grid-column: 1 / -1; margin-top: 14px; }
.dsd-empty {
  color: var(--dsd-muted);
  font-size: 12.5px;
  padding: 6px 0;
}
.dsd-alert {
  margin-top: 14px;
  padding: 12px 14px;
  border: 1px solid #f3c6c1;
  border-radius: 10px;
  background: #fff5f4;
  color: var(--dsd-danger);
  font-size: 12.5px;
  overflow-wrap: anywhere;
}
.dsd-install-panel {
  margin-top: 18px;
  border: 1px solid var(--dsd-line);
  border-radius: 12px;
  background: var(--dsd-surface);
  overflow: hidden;
}
.dsd-install-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--dsd-line);
  background: #fbfdff;
}
.dsd-install-title { font-weight: 600; font-size: 12.5px; }
.dsd-install-state {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--dsd-muted);
}
.dsd-install-state.is-running { color: var(--dsd-accent); }
.dsd-install-state.is-succeeded { color: #0f766e; }
.dsd-install-state.is-failed { color: var(--dsd-danger); }
.dsd-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(37, 99, 235, 0.25);
  border-top-color: var(--dsd-accent);
  border-radius: 50%;
  animation: dsd-spin 0.8s linear infinite;
}
@keyframes dsd-spin { to { transform: rotate(360deg); } }
.dsd-log {
  margin: 0;
  max-height: 300px;
  min-height: 96px;
  overflow: auto;
  padding: 12px 16px;
  background: #f8fafc;
  color: #334155;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.dsd-log.is-empty { color: #94a3b8; }
.dsd-log-hint {
  padding: 8px 16px 12px;
  color: var(--dsd-muted);
  font-size: 11.5px;
  border-top: 1px dashed var(--dsd-line);
}
.dsd-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 36px 0;
  color: var(--dsd-muted);
  font-size: 12.5px;
}
.dsd-link-note {
  margin-top: 12px;
  color: var(--dsd-muted);
  font-size: 11.5px;
  overflow-wrap: anywhere;
}

/* ---------- dataset ---------- */
.dsd-menu-sub .dsd-menu-item {
  padding: 6px 9px;
  font-size: 12.5px;
  color: #42536b;
}
.dsd-menu-sub .dsd-menu-item svg { flex: 0 0 auto; opacity: 0.7; }
.dsd-menu-sub .dsd-menu-item.is-active { color: var(--dsd-accent); }
.dsd-menu-sub-name {
  flex: 0 0 auto;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 10px;
  color: #96a5bc;
  white-space: nowrap;
  overflow: hidden;
}
.dsd-menu-item.is-active .dsd-menu-sub-name { color: var(--dsd-accent); }
.dsd-page-wide { max-width: 1240px; }
.dsd-page-table-name {
  margin-left: 10px;
  font-size: 13px;
  font-weight: 400;
  color: var(--dsd-muted);
}
.dsd-fact-list {
  margin: 12px 0 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12.5px;
  color: #42536b;
}
.dsd-alert-warn {
  border-color: #f0d9b5;
  background: #fffaf1;
  color: var(--dsd-warn);
}

/* SQL 编辑区 */
.dsd-sql-panel {
  margin-top: 14px;
  border: 1px solid var(--dsd-line);
  border-radius: 12px;
  background: var(--dsd-surface);
  overflow: hidden;
}
.dsd-sql-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--dsd-line);
  background: #fbfdff;
}
.dsd-sql-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--dsd-muted);
}
.dsd-sql-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: 0;
  padding: 12px 14px;
  resize: vertical;
  min-height: 64px;
  max-height: 240px;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  color: #1e293b;
  background: #fff;
  outline: none;
}
.dsd-sql-input.is-invalid { background: #fff8f7; }
.dsd-sql-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-top: 1px dashed var(--dsd-line);
}
.dsd-sql-error { font-size: 11.5px; color: var(--dsd-danger); }

/* 结果表格：横向与纵向都可滚动 */
.dsd-result-panel {
  margin-top: 14px;
  border: 1px solid var(--dsd-line);
  border-radius: 12px;
  background: var(--dsd-surface);
  overflow: hidden;
}
.dsd-grid-scroll {
  overflow: auto;
  max-width: 100%;
}
.dsd-result-scroll { max-height: 480px; }
.dsd-grid {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  font-size: 12px;
}
.dsd-grid th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: 8px 12px;
  background: #f4f8fe;
  border-bottom: 1px solid var(--dsd-line);
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
  color: #3b4c63;
  text-align: left;
  white-space: nowrap;
}
.dsd-grid td {
  padding: 6px 12px;
  border-bottom: 1px solid #eef2f8;
  color: #2c3a4f;
  white-space: nowrap;
}
.dsd-grid tbody tr:hover td { background: #f6faff; }
.dsd-grid td.is-num, .dsd-grid th.is-num {
  text-align: right;
  font-family: "Cascadia Mono", Consolas, monospace;
}
.dsd-grid td.is-null {
  color: #a3b1c6;
  font-style: italic;
}
.dsd-grid td.is-text {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dsd-grid .dsd-grid-index {
  color: #9aa9bf;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 10.5px;
  text-align: right;
  background: #fafcfe;
}
.dsd-grid tr.is-link { cursor: pointer; }
.dsd-grid tr.is-link:hover td { background: var(--dsd-accent-soft); }
.dsd-table-scale { margin-top: 12px; }
.dsd-table-scale .dsd-grid-scroll { max-height: 320px; }

/* 底部统计条 */
.dsd-result-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border-top: 1px solid var(--dsd-line);
  background: #fbfdff;
  font-size: 11.5px;
  color: var(--dsd-muted);
}
.dsd-stat-sep {
  width: 1px;
  height: 12px;
  background: var(--dsd-line);
}

/* 字段说明 */
.dsd-columns { margin-top: 14px; }
.dsd-column-list {
  margin-top: 6px;
  max-height: 220px;
  overflow-y: auto;
  padding: 8px 12px;
  border: 1px solid var(--dsd-line);
  border-radius: 8px;
  background: #fbfdff;
}
.dsd-column-row {
  display: flex;
  gap: 12px;
  align-items: baseline;
  padding: 2px 0;
  font-size: 11.5px;
}
.dsd-column-name { flex: 0 0 150px; color: #334155; }
.dsd-column-type { flex: 0 0 70px; color: #96a5bc; font-size: 10.5px; }
.dsd-column-comment { flex: 1 1 auto; min-width: 0; color: var(--dsd-muted); }

/* ---------- relation graph ---------- */
.dsd-graph-scroll {
  margin-top: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.dsd-graph {
  display: block;
  width: 100%;
  min-width: 760px;
  height: auto;
}
.dsd-graph-edge {
  fill: none;
  stroke: #9fb4d0;
  stroke-width: 1.2;
}
.dsd-graph-label {
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 9.5px;
  fill: var(--dsd-muted);
}
.dsd-graph-node {
  fill: #fbfdff;
  stroke-width: 1.4;
}
.dsd-graph-name {
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--dsd-ink);
}
.dsd-graph-sub {
  font-size: 10px;
  fill: var(--dsd-muted);
}
.dsd-graph-count {
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 9.5px;
  fill: var(--dsd-accent);
}
.dsd-graph-domain { font-size: 9px; }

/* 知识图谱：域卡片 + 三元组表 */
.dsd-domain-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.dsd-domain-card {
  border: 1px solid var(--dsd-line);
  border-top: 3px solid var(--dsd-accent);
  border-radius: 10px;
  padding: 10px 12px;
  background: var(--dsd-surface);
}
.dsd-domain-title {
  font-size: 11.5px;
  font-weight: 600;
}
.dsd-domain-entity {
  margin-top: 6px;
  font-size: 12px;
  color: #2c3a4f;
}
.dsd-domain-note {
  margin-top: 8px;
  font-size: 10.5px;
  line-height: 1.55;
  color: var(--dsd-muted);
}
.dsd-triple-scroll { margin-top: 12px; }
.dsd-triple-relation { color: var(--dsd-accent); }

/* 滚动条统一样式：默认深色滚动条在浅色面板里过于突兀 */
.dsd-grid-scroll::-webkit-scrollbar,
.dsd-graph-scroll::-webkit-scrollbar,
.dsd-result-scroll::-webkit-scrollbar,
.dsd-column-list::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
.dsd-grid-scroll::-webkit-scrollbar-thumb,
.dsd-graph-scroll::-webkit-scrollbar-thumb,
.dsd-result-scroll::-webkit-scrollbar-thumb,
.dsd-column-list::-webkit-scrollbar-thumb {
  background: #c7d5e8;
  border-radius: 4px;
}
.dsd-grid-scroll::-webkit-scrollbar-track,
.dsd-graph-scroll::-webkit-scrollbar-track,
.dsd-result-scroll::-webkit-scrollbar-track,
.dsd-column-list::-webkit-scrollbar-track {
  background: #f2f6fc;
}

/* ---------- 数据科学文档 ---------- */
.dsd-menu-nested {
  margin-top: 2px;
}
.dsd-menu-sub-deep {
  padding-left: 14px;
}
.dsd-menu-sub-deep .dsd-menu-item {
  font-size: 12px;
}
.dsd-doc-head {
  margin: 0 auto 14px;
  max-width: 980px;
  padding: 0 4px;
}
.dsd-doc-head h1 {
  margin: 6px 0 6px;
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.2px;
}
.dsd-doc-path {
  margin: 0;
  color: var(--dsd-muted);
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11.5px;
}
.dsd-doc-card {
  margin: 0 auto;
  max-width: 980px;
  padding: 30px 38px 40px;
}
.dsd-doc-loading,
.dsd-doc-error {
  margin: 0 auto;
  max-width: 980px;
  padding: 26px;
  color: var(--dsd-muted);
}
.dsd-doc-error {
  color: var(--dsd-danger);
}
.dsd-doc-error .dsd-button {
  margin-top: 12px;
}

.dsd-md {
  color: var(--dsd-ink);
  font-size: 13.5px;
  line-height: 1.75;
}
.dsd-md-h1,
.dsd-md-h2,
.dsd-md-h3,
.dsd-md-h4 {
  margin: 26px 0 12px;
  font-weight: 640;
  line-height: 1.4;
  letter-spacing: -0.2px;
}
.dsd-md-h1 {
  margin-top: 0;
  font-size: 20px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--dsd-line);
}
.dsd-md-h2 {
  font-size: 17px;
  padding-left: 10px;
  border-left: 3px solid var(--dsd-accent);
}
.dsd-md-h3 {
  font-size: 15px;
  color: #22324d;
}
.dsd-md-h4 {
  font-size: 13.5px;
  color: var(--dsd-muted);
}
.dsd-md-text {
  margin: 10px 0;
}
.dsd-md-list {
  margin: 10px 0;
  padding-left: 20px;
}
.dsd-md-list li {
  margin: 5px 0;
}
.dsd-md-quote {
  margin: 12px 0;
  padding: 10px 14px;
  border-left: 3px solid #b9cdec;
  background: #f6f9ff;
  color: #45536b;
  border-radius: 0 6px 6px 0;
}
.dsd-md-rule {
  margin: 20px 0;
  border: none;
  border-top: 1px solid var(--dsd-line);
}
.dsd-md-pre {
  margin: 12px 0;
  padding: 14px 16px;
  background: #f4f7fb;
  border: 1px solid var(--dsd-line);
  border-radius: 8px;
  overflow: auto;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
}
.dsd-md-code-inline {
  padding: 1px 5px;
  border-radius: 4px;
  background: #eef3fb;
  color: #274690;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
}
.dsd-md-link {
  color: var(--dsd-accent);
  text-decoration: none;
  cursor: pointer;
  border-bottom: 1px solid rgba(37, 99, 235, 0.28);
}
.dsd-md-link:hover {
  color: #1d4ed8;
  border-bottom-color: #1d4ed8;
}
.dsd-md-anchor {
  color: var(--dsd-muted);
}
.dsd-md-table-wrap {
  margin: 14px 0;
  overflow-x: auto;
  border: 1px solid var(--dsd-line);
  border-radius: 8px;
}
.dsd-md-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.dsd-md-table th {
  padding: 9px 12px;
  background: #f2f6fd;
  text-align: left;
  font-weight: 600;
  color: #22324d;
  border-bottom: 1px solid var(--dsd-line);
  white-space: nowrap;
}
.dsd-md-table td {
  padding: 9px 12px;
  border-bottom: 1px solid #edf2f9;
  vertical-align: top;
}
.dsd-md-table tbody tr:last-child td {
  border-bottom: none;
}
.dsd-md-table tbody tr:nth-child(even) {
  background: #fbfcfe;
}
.dsd-md-figure {
  margin: 18px 0;
  padding: 12px;
  border: 1px solid var(--dsd-line);
  border-radius: 10px;
  background: #fcfdff;
}
.dsd-md-figure img {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 6px;
}
.dsd-md-figure figcaption {
  margin-top: 8px;
  text-align: center;
  color: var(--dsd-muted);
  font-size: 12px;
}
.dsd-md-image-inline {
  max-width: 100%;
  vertical-align: middle;
}

@media (max-width: 1100px) {
  .dsd-hero-art { display: none; }
}
@media (max-width: 760px) {
  .dsd-features, .dsd-kv-grid, .dsd-package-list { grid-template-columns: minmax(0, 1fr); }
  .dsd-domain-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dsd-main { padding: 20px 18px 32px; }
}
`
