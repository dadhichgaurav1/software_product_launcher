# Extension icons

The manifest references three PNG icons:

- `icon16.png` — 16×16 (toolbar / favicon size)
- `icon48.png` — 48×48 (extensions management page)
- `icon128.png` — 128×128 (install dialog / Chrome Web Store)

**These PNGs are not committed yet, and that's fine** — Chrome falls back to a
default placeholder icon when they are missing, and the extension loads and works
normally without them.

To add real icons, drop the three files into this folder using exactly those
names. A single square logo exported at 16/48/128 px is enough; the manifest's
`icons` block already points at them, so no manifest change is needed.
