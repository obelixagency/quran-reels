"""Daily Serenity – reel design (1080×1920).

Calm nature video, darkened; the English text fades in word by word (Quran: in sync with the LibriVox
reader; hadith / dua: at a gentle reading pace). Brand colours and fonts from the brief:
Cormorant Garamond Italic for the main text, Jost for labels.
"""
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..common import ROOT, run
from ..render import compose  # same proven FFmpeg pipeline as the Arabic reels

FONTS = ROOT / "assets" / "fonts" / "en"
W, H = 1080, 1920
BEIGE = (243, 235, 221, 255)
GOLD_L = (217, 190, 133, 255)
WHITE = (255, 255, 255, 255)
FADE = 0.45


def font(name, size, weight=None):
    f = ImageFont.truetype(str(FONTS / name), size, layout_engine=ImageFont.Layout.BASIC)
    if weight:
        try:
            f.set_variation_by_axes([weight])
        except Exception:  # static font
            pass
    return f


def serif(size):
    return font("CormorantGaramond-Italic.ttf", size, 500)


def sans(size, weight=450):
    return font("Jost.ttf", size, weight)


def for_video(text):
    """No Arabic text in the videos: ﷺ becomes an English phrase."""
    return re.sub(r"\s*ﷺ", " (peace be upon him)", text)


def _spaced(d, xy, text, f, fill, spacing):
    """Letter-spaced, centred label."""
    widths = [f.getlength(ch) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = xy[0] - total / 2
    for ch, w in zip(text, widths):
        d.text((x, xy[1]), ch, font=f, fill=fill, anchor="lm")
        x += w + spacing


def _wrap(words, f, max_w):
    lines, cur = [], []
    for w in words:
        if cur and f.getlength(" ".join(cur + [w])) > max_w:
            lines.append(cur)
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def build(*, label, intro, text, ref, credit, times=None, duration=None):
    """Returns a Timeline-compatible object. times: per-word (start, end) or None (auto pacing)."""
    words = text.split()
    size = 78
    while True:
        f = serif(size)
        lines = _wrap(words, f, W - 190)
        lh = int(size * 1.34)
        if len(lines) * lh <= H * 0.46 or size <= 40:
            break
        size -= 2
    f_label, f_intro, f_ref, f_small = sans(34, 500), serif(max(36, int(size * 0.62))), sans(34, 420), sans(26, 380)
    intro_lines = [" ".join(l) for l in _wrap(intro.split(), f_intro, W - 220)] if intro else []
    intro_h = int(f_intro.size * 1.35) * len(intro_lines) + (int(f_intro.size * 0.4) if intro else 0)
    text_h = len(lines) * lh
    block = 70 + intro_h + text_h + 40 + 60 + 76
    top = int(H * 0.46) - block // 2
    cx = W // 2

    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((64, top - 70, W - 64, top + block + 60), radius=46,
                                            fill=(20, 28, 24, 150))
    base = panel.filter(ImageFilter.GaussianBlur(22))
    d = ImageDraw.Draw(base)
    _spaced(d, (cx, top + 10), label.upper(), f_label, GOLD_L, 9)
    y = top + 70
    for k, il in enumerate(intro_lines):
        d.text((cx, y + int(f_intro.size * 1.35) * k + f_intro.size // 2), il, font=f_intro,
               fill=(236, 230, 214, 235), anchor="mm")
    y += intro_h
    ty = y
    y += text_h + 40
    d.line((cx - 120, y, cx + 120, y), fill=GOLD_L[:3] + (160,), width=2)
    d.text((cx, y + 44), ref, font=f_ref, fill=GOLD_L, anchor="mm")
    cl = [credit] if f_small.getlength(credit) <= W - 220 else credit.split(" · ")
    for k, c in enumerate(cl):
        d.text((cx, y + 96 + k * 36), c, font=f_small, fill=(236, 230, 214, 170), anchor="mm")
    _spaced(d, (cx, H - 250), "DAILY SERENITY", sans(30, 500), (243, 235, 221, 200), 12)

    # one sprite per word (with a soft shadow)
    sprites = []
    for li, ln in enumerate(lines):
        cy = ty + li * lh + lh // 2
        line = " ".join(ln)
        lw = f.getlength(line)
        x = cx - lw / 2
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.text((cx + 2, cy + 3), line, font=f, fill=(0, 0, 0, 170), anchor="mm")
        layer = layer.filter(ImageFilter.GaussianBlur(4))
        ImageDraw.Draw(layer).text((cx, cy), line, font=f, fill=WHITE, anchor="mm")
        for w in ln:
            ww = f.getlength(w)
            box = (max(0, int(x - 6)), int(cy - lh * 0.62), min(W, int(x + ww + 8)), int(cy + lh * 0.62))
            sprites.append((layer.crop(box), box[0], box[1]))
            x += ww + f.getlength(" ")

    n = len(sprites)
    if times is None:  # hadith / dua: calm reading pace
        start, per = 1.2, max(0.16, min(0.34, (duration * 0.55) / max(1, n)))
        times = [(start + i * per, start + (i + 1) * per) for i in range(n)]
    return EnTimeline(base, sprites, times, duration)


class EnTimeline:
    def __init__(self, base, sprites, times, total):
        self.base, self.sprites, self.times, self.total = base, sprites, times, total

    def state(self, t):
        ba = round(min(1.0, t / 0.6, max(0.0, (self.total - t) / 0.8)), 2)
        ops = [("b", ba)]
        for k, (ws, _) in enumerate(self.times):
            p = round(min(1.0, max(0.0, (t - ws + 0.05) / FADE)), 2)
            if p > 0:
                ops.append((k, round(p * ba, 2)))
        return tuple(ops)

    @staticmethod
    def _alpha(img, m):
        if m >= 1:
            return img
        a = np.array(img)
        a[..., 3] = (a[..., 3].astype(np.float32) * m).astype(np.uint8)
        return Image.fromarray(a, "RGBA")

    def render(self, ops, W_, H_):
        c = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        for k, m in ops:
            if k == "b":
                c.alpha_composite(self._alpha(self.base, m))
            else:
                s, x, y = self.sprites[k]
                c.alpha_composite(self._alpha(s, m), dest=(x, y))
        return c

    def still(self):
        return self.render((("b", 1.0), *((k, 1.0) for k in range(len(self.sprites)))), W, H)


def ambient(dest, total, voice=None):
    """Soft, copyright-free ambience generated with FFmpeg (gentle 'ocean' swell).
    With a voice track it is mixed very low underneath the reader."""
    amb = (f"anoisesrc=color=brown:amplitude=0.5:duration={total:.2f}:sample_rate=44100,"
           f"lowpass=f=700,highpass=f=50,volume='0.55+0.35*sin(2*PI*t/8.5)':eval=frame,"
           f"afade=t=in:d=1.5,afade=t=out:st={max(0.1, total - 2):.2f}:d=2")
    if voice:
        fc = f"{amb},volume=0.07[amb];[0:a]volume=1.0[v];[v][amb]amix=inputs=2:duration=first:normalize=0[out]"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice), "-filter_complex", fc,
             "-map", "[out]", "-ac", "2", "-ar", "44100", str(dest)])
    else:
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"{amb},volume=0.35,loudnorm=I=-24",
             "-ac", "2", "-ar", "44100", "-t", f"{total:.2f}", str(dest)])
    return dest


def cover(background, timeline, dest):
    """Cover image: a frame of the background + the full text."""
    frame = dest.with_suffix(".bg.jpg")
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(background), "-frames:v", "1",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=black@0.3:t=fill", str(frame)])
    img = Image.open(frame).convert("RGBA")
    img.alpha_composite(timeline.still())
    img.convert("RGB").save(dest, quality=92)
    frame.unlink(missing_ok=True)
    return dest


def render(*, background, timeline, audio, total, dest, cfg):
    v = cfg["video"]
    return compose(background=background, timeline=timeline, audio=audio, total=total, dest=dest,
                   W=W, H=H, fps=v.get("fps", 30), darken=v.get("background_darken", 0.3))
