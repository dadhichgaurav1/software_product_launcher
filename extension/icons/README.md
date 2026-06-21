# Extension icons

The manifest references three PNG icons, and they are committed in this folder:

- `icon16.png` — 16×16 (toolbar / favicon size)
- `icon48.png` — 48×48 (extensions management page)
- `icon128.png` — 128×128 (install dialog / Chrome Web Store)

> Note: Chrome **fails to load the manifest** if an icon referenced in the
> `icons` block is missing (it does *not* fall back to a default), so these files
> must exist for the extension to load.

To regenerate or replace them, run the generator (requires Pillow) or drop in
your own square PNGs using exactly these names — the manifest already points at
them, so no manifest change is needed:

```bash
python3 - <<'PY'
from PIL import Image, ImageDraw
ACCENT, WHITE = (108,140,255,255), (255,255,255,255)
def make(size):
    S=size*4; img=Image.new("RGBA",(S,S),(0,0,0,0)); d=ImageDraw.Draw(img)
    d.rounded_rectangle([0,0,S-1,S-1],radius=int(S*0.22),fill=ACCENT)
    cx=S/2; hw,ht,hb=S*0.52,S*0.20,S*0.52
    d.polygon([(cx,ht),(cx-hw/2,hb),(cx+hw/2,hb)],fill=WHITE)
    sw=S*0.18; d.rectangle([cx-sw/2,hb-S*0.03,cx+sw/2,S*0.80],fill=WHITE)
    return img.resize((size,size),Image.LANCZOS)
for s in (16,48,128): make(s).save(f"icon{s}.png")
PY
```
