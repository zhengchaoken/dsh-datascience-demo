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
.dsd-banner-status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin-left: auto;
  flex: 0 0 auto;
  padding: 5px 11px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--dsd-line);
  background: rgba(255, 255, 255, 0.8);
  color: var(--dsd-muted);
}
.dsd-banner-status.is-ok { color: #0f766e; border-color: #b7e2da; background: #f0fbf9; }
.dsd-banner-status.is-warning { color: var(--dsd-warn); border-color: #f0d9b5; background: #fffaf1; }
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
.dsd-env-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.dsd-card {
  padding: 16px 18px;
  border: 1px solid var(--dsd-line);
  border-radius: 12px;
  background: var(--dsd-surface);
  min-width: 0;
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

@media (max-width: 1100px) {
  .dsd-env-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .dsd-hero-art { display: none; }
}
@media (max-width: 760px) {
  .dsd-env-grid, .dsd-features { grid-template-columns: minmax(0, 1fr); }
  .dsd-main { padding: 20px 18px 32px; }
}
`
