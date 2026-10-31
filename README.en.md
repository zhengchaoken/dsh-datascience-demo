# dsh-datascience-demo

A **Data Science Demo** plugin for DeepSeek Harness (DSH). Package name
`dsh-datascience-demo`, plugin id `datascience-demo`.

Once installed, a **数据科学示例** entry appears in the sidebar's plugins area.
Clicking it opens a blank panel in the main column.

## Layout

```text
src/index.ts         host half (cordis plugin row, no host capability yet)
src/client/index.ts  browser half: sidebar entry + blank main panel
scripts/build.ts     esbuild build script
cordis.patch.yml     bundle patch inserting the plugin row
lib/                 build output (index.js / client.js)
```

The plugin uses only official DSH slots:

- `sidebar.panellist` — sidebar entry with id `datascience-demo`
- `main` (keyed) — blank panel with the same key

## Build and package

```bash
npm install
npm run build
npm run typecheck
npm pack   # produces dsh-datascience-demo-0.1.0.tgz
```

## Manual install into dsh desktop

The `desktop` profile is owned by the Electron application, so `dsh plugin`
cannot manage it. Install manually:

1. Put the plugin under
   `%USERPROFILE%\.dsh\profiles\desktop\node_modules\dsh-datascience-demo`
   (copy the unpacked `package/` from the tgz, or create a directory junction
   to this checkout for development).
2. Add `"dsh-datascience-demo"` to `dsh.profile.bundles` in
   `%USERPROFILE%\.dsh\profiles\desktop\package.json`.
3. Fully quit and restart DeepSeek Harness.

The sidebar entry should then appear. See [README.md](README.md) for the
detailed PowerShell steps and uninstall instructions.
