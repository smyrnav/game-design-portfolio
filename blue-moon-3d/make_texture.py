"""Build the blue-moon asset set:
- moon_eq.jpg     : NASA LROC equirectangular Moon color map, re-graded into the
                    exact blue palette of the user's reference photo
- moon_height.png : real LOLA elevation (seamless), for displacement
- moon_normal.png : tangent-space normal map derived from the elevation

Sources (NASA SVS CGI Moon Kit, public domain):
  lroc_color_poles_2k.tif, ldem_4.tif
"""
import numpy as np
from PIL import Image

DIR = "/home/seyrin/Downloads/blue-moon-3d"
REF = "/home/seyrin/Downloads/01a9694073cc4ef16ffda061b6dfd2f3.jpg"

# ---------- 1. palette LUT from the reference photo ----------
ref = np.asarray(Image.open(REF).convert("RGB")).astype(np.float64) / 255.0
h, w, _ = ref.shape
lum = ref.mean(axis=2)
cy0, cx0 = h // 2, w // 2
xs = np.nonzero(lum[cy0] > 0.31)[0]
ys = np.nonzero(lum[:, cx0] > 0.31)[0]
cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
r = min(xs.max() - xs.min(), ys.max() - ys.min()) / 2
gy, gx = np.mgrid[0:h, 0:w]
inside = ((gx - cx) ** 2 + (gy - cy) ** 2) <= (r * 0.98) ** 2

bins = np.clip((lum[inside] * 255).astype(int), 0, 255)
lut = np.zeros((256, 3))
cnt = np.bincount(bins, minlength=256).clip(1)
for c in range(3):
    lut[:, c] = np.bincount(bins, ref[inside][:, c], minlength=256) / cnt
# fill empty bins by interpolation, then smooth
have = np.bincount(bins, minlength=256) > 0
xs_all = np.arange(256)
for c in range(3):
    lut[:, c] = np.interp(xs_all, xs_all[have], lut[have, c])
    lut[:, c] = np.convolve(lut[:, c], np.ones(7) / 7, mode="same")
lut = lut.astype(np.float32)

# ---------- 2. re-grade the NASA color map ----------
col = np.asarray(Image.open(f"{DIR}/lroc_color_poles_8k.tif").convert("RGB")).astype(np.float32) / 255.0
cl = col.mean(axis=2)
lo, hi = np.percentile(cl, 0.5), np.percentile(cl, 99.7)
cl = np.clip((cl - lo) / (hi - lo), 0, 1)                    # contrast stretch

graded = lut[np.clip((cl * 255).astype(int), 0, 255)]
mean = graded.mean(axis=-1, keepdims=True)
graded = np.clip(mean + (graded - mean) * 1.3, 0, 1)   # saturation to match reference
graded = 1 - (1 - graded) / 1.12                       # soft luminosity lift
Image.fromarray((graded * 255).astype(np.uint8)).save(f"{DIR}/moon_eq.jpg", quality=90)

# ---------- 3. height map from real elevation ----------
dem = np.asarray(Image.open(f"{DIR}/ldem_16.tif")).astype(np.float64)
dem_img = Image.fromarray(dem.astype(np.float32)).resize((4096, 2048), Image.BILINEAR)
dem = np.asarray(dem_img)
h0, h1 = np.percentile(dem, 0.2), np.percentile(dem, 99.8)
height = np.clip((dem - h0) / (h1 - h0), 0, 1)
Image.fromarray((height * 255).astype(np.uint8)).save(f"{DIR}/moon_height.png")

# ---------- 3b. ambient occlusion: low areas (cavity floors, mare pits)
# receive less ambient light -> cavities read as deep, not painted matte
ao = 0.3 + 0.7 * height ** 0.8
Image.fromarray((ao * 255).astype(np.uint8)).save(f"{DIR}/moon_ao.png")

# ---------- 4. normal map (wrap-aware in longitude) ----------
# fuse real elevation with photographic micro-relief: the color map shows small
# craters (esp. in the dark maria) that the laser DEM smooths away
def gauss_f(a, sigma):
    Hh, Ww = a.shape
    fy = np.fft.fftfreq(Hh)[:, None]
    fx = np.fft.rfftfreq(Ww)[None, :]
    g = np.exp(-2 * (np.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))
    return np.fft.irfft2(np.fft.rfft2(a) * g, s=(Hh, Ww))

cl_small = np.asarray(Image.fromarray(cl.astype(np.float32), mode="F").resize((4096, 2048), Image.BILINEAR))
photo_detail = cl_small - gauss_f(cl_small, 6.0)
# clamp outliers so JPEG noise can't turn into grain
lim = 3 * photo_detail.std()
photo_detail = np.clip(photo_detail, -lim, lim)
# dark maria get extra micro-relief weight, without amplifying noise
detail_w = 0.8 + 1.6 * (1 - cl_small)
height_n = height + photo_detail * detail_w
height_n = gauss_f(height_n, 1.0)   # kill single-pixel facets -> no sun sparkle

k = 8.0
gxm = (np.roll(height_n, -1, axis=1) - np.roll(height_n, 1, axis=1)) * 0.5
gym = (np.roll(height_n, -1, axis=0) - np.roll(height_n, 1, axis=0)) * 0.5
n = np.stack([-gxm * k, gym * k, np.ones_like(height_n)], axis=-1)
n /= np.linalg.norm(n, axis=-1, keepdims=True)
Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(f"{DIR}/moon_normal.png")

# ---------- 5b. emissive map: the self-glow must be occluded like real light.
# Multiplying by AO keeps cavity floors dark instead of uniformly luminous.
emis = np.asarray(Image.fromarray((graded * 255).astype(np.uint8)).resize((4096, 2048), Image.BILINEAR)).astype(np.float32) / 255.0
emis = np.clip(emis * ao[..., None], 0, 1)
Image.fromarray((emis * 255).astype(np.uint8)).save(f"{DIR}/moon_emis.jpg", quality=90)

# ---------- 6. roughness map: dark maria get a satin sheen (lower roughness)
# so the accent light reveals their relief; bright highlands stay matte
rough = np.clip(0.5 + 0.5 * cl_small, 0, 1)
Image.fromarray((rough * 255).astype(np.uint8)).save(f"{DIR}/moon_rough.png")

print("wrote moon_eq.jpg, moon_height.png, moon_normal.png, moon_emis.jpg")
