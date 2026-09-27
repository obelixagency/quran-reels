"""تصميم الريل: الآية بتتكتب كلمة بكلمة مع صوت الشيخ + خلفية طبيعة متحركة بهدوء.

أنماط ظهور النص (config.json → video.text_style):
  "write"     : كل كلمة بتتكتب من اليمين للشمال في نفس لحظة نطق الشيخ ليها (الافتراضي)
  "highlight" : الآية كلها ظاهرة باهت، والكلمة اللي بتتقري بتنوّر دهبي، واللي اتقرت تبقى أبيض
  "static"    : الآية كلها تظهر مرة واحدة
"""
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import ROOT, ar_num, media_duration, run

FONTS = ROOT / "assets" / "fonts"
QURAN_FONT = FONTS / "AmiriQuran-Regular.ttf"
UI_FONT = FONTS / "Amiri-Regular.ttf"
UI_BOLD = FONTS / "Amiri-Bold.ttf"

LEAD, GAP, TAIL = 0.7, 0.45, 1.4  # seconds of silence: before first ayah / between ayat / after last

GOLD = (236, 214, 160, 255)
WHITE = (255, 255, 255, 255)
FADE = 0.4


FONT_URLS = {
    QURAN_FONT: "https://github.com/google/fonts/raw/main/ofl/amiriquran/AmiriQuran-Regular.ttf",
    UI_FONT: "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
    UI_BOLD: "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf",
}


def _font(path, size):
    if not path.exists():  # الخطوط مجانية (OFL) وبتتحمّل تلقائيًا من Google Fonts لو مش موجودة
        from .common import download
        download(FONT_URLS[path], path)
    return ImageFont.truetype(str(path), size, layout_engine=ImageFont.Layout.RAQM)


# ============================================================== layout
def _wrap(tokens, font, max_w):
    lines, cur = [], []
    for tok in tokens:
        trial = " ".join(cur + [tok])
        if not cur or font.getlength(trial, direction="rtl") <= max_w:
            cur.append(tok)
        else:
            lines.append(cur)
            cur = [tok]
    if cur:
        lines.append(cur)
    return lines


def _fit(tokens, max_w, max_h, start=104, minimum=40):
    size = start
    while True:
        font = _font(QURAN_FONT, size)
        lines = _wrap(tokens, font, max_w)
        line_h = int(size * 1.85)
        if len(lines) * line_h <= max_h or size <= minimum:
            return font, lines, line_h
        size -= 2


def _line_layer(W, H, text, font, cx, cy, color):
    """One line of Quran text (with a soft shadow) on a transparent full-size layer."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((cx + 3, cy + 4), text, font=font, fill=(0, 0, 0, 190), anchor="mm", direction="rtl")
    layer = layer.filter(ImageFilter.GaussianBlur(5))
    ImageDraw.Draw(layer).text((cx, cy), text, font=font, fill=color, anchor="mm", direction="rtl")
    return layer


def build_card(*, words, ayah_no, surah_name, reciter_name, style, W=1080, H=1920, watermark=""):
    """Returns {"base": RGBA, "white": [(sprite,x,y)], "gold": [(sprite,x,y)]} – one sprite per token."""
    tokens = list(words) + ([f"۝{ar_num(ayah_no)}"] if ayah_no else [])
    font, lines, line_h = _fit(tokens, W - 190, int(H * 0.42))

    f_surah, f_reciter = _font(UI_BOLD, 50), _font(UI_FONT, 44)
    label = f"سورة {surah_name}" + ("" if not ayah_no else f"  •  الآية {ar_num(ayah_no)}")
    reciter = f"بصوت الشيخ {reciter_name}"

    text_h = len(lines) * line_h
    footer_h = 58 + 70 + 62
    block_h = text_h + footer_h
    top = int(H * 0.43) - block_h // 2
    cx = W // 2

    # ---- panel + footer
    panel = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle((58, top - 58, W - 58, top + block_h + 52), radius=50,
                                            fill=(0, 0, 0, 140))
    base = panel.filter(ImageFilter.GaussianBlur(20))
    d = ImageDraw.Draw(base)
    y = top + text_h + 36
    d.line((cx - 170, y, cx + 170, y), fill=(236, 214, 160, 170), width=2)
    y += 22
    d.text((cx, y + 35), label, font=f_surah, fill=GOLD, anchor="mm", direction="rtl")
    y += 70
    d.text((cx, y + 31), reciter, font=f_reciter, fill=(255, 255, 255, 225), anchor="mm", direction="rtl")
    if watermark:
        d.text((cx, H - 330), watermark, font=_font(UI_FONT, 36), fill=(255, 255, 255, 140), anchor="mm")

    # ---- text: one layer per line, then cut into word sprites
    white, gold = [], []
    space = font.getlength(" ")
    for li, toks in enumerate(lines):
        cy = top + li * line_h + line_h // 2
        text = " ".join(toks)
        lw = font.getlength(text, direction="rtl")
        widths = [font.getlength(t, direction="rtl") for t in toks]
        f = lw / (sum(widths) + space * (len(toks) - 1))
        right = cx + lw / 2
        layers = {"white": _line_layer(W, H, text, font, cx, cy, WHITE)}
        if style == "highlight":
            layers["gold"] = _line_layer(W, H, text, font, cx, cy, GOLD)
        if style == "static":
            base.alpha_composite(layers["white"])
        elif style == "highlight":
            dim = layers["white"].copy()
            dim.putalpha(dim.getchannel("A").point(lambda a: int(a * 0.42)))
            base.alpha_composite(dim)

        y0, y1 = int(cy - line_h * 0.62), int(cy + line_h * 0.62)
        cum = 0.0
        for j, w in enumerate(widths):
            r = right - cum * f + (space * f / 2 if j else 30)
            left = right - (cum + w) * f - (space * f / 2 if j < len(toks) - 1 else 30)
            box = (max(0, int(left)), max(0, y0), min(W, int(r + 1)), min(H, y1))
            white.append((layers["white"].crop(box), box[0], box[1]))
            if "gold" in layers:
                gold.append((layers["gold"].crop(box), box[0], box[1]))
            cum += w + space
    return {"base": base, "white": white, "gold": gold, "n_tokens": len(tokens)}


# ============================================================== audio
def build_audio(segments, dest):
    """segments: list of mp3 paths → one wav with lead/gap/tail silences + loudness normalisation.
    Returns (dest, [(start, end) per segment], total_duration)."""
    durs = [media_duration(p) for p in segments]
    inputs, parts = [], []
    for i, p in enumerate(segments):
        inputs += ["-i", str(p)]
        pad = GAP if i < len(segments) - 1 else TAIL
        parts.append(f"[{i}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"apad=pad_dur={pad}[a{i}]")
    total = LEAD + sum(durs) + GAP * (len(durs) - 1) + TAIL
    chain = "".join(f"[a{i}]" for i in range(len(segments)))
    fc = ";".join(parts) + f";{chain}concat=n={len(segments)}:v=0:a=1,adelay={int(LEAD*1000)}:all=1," \
         f"loudnorm=I=-15:TP=-1.5:LRA=11,aresample=44100,afade=t=out:st={total-0.9:.2f}:d=0.9,atrim=0:{total:.3f}[out]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", fc, "-map", "[out]", "-ac", "2", str(dest)])

    times, t = [], LEAD
    for d in durs:
        times.append((t, t + d))
        t += d + GAP
    return dest, times, total


# ============================================================== animation
def _scaled(sprite, mult):
    """Multiply sprite alpha by mult (scalar or per-column numpy vector)."""
    arr = np.array(sprite)
    a = arr[..., 3].astype(np.float32)
    if np.isscalar(mult):
        a *= mult
    else:
        a *= mult[None, :]
    arr[..., 3] = np.clip(a, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def _wipe_mask(width, p, soft=28.0):
    """Right→left reveal: returns per-column alpha multipliers for progress p (0..1)."""
    edge = width * (1.0 - p)
    x = np.arange(width, dtype=np.float32)
    return np.clip((x - edge + soft) / soft, 0.0, 1.0)


class Timeline:
    def __init__(self, cards, style, total):
        """cards: list of {"card": build_card(...), "window": (t0, t1), "words": [(ws, we) absolute per token]}"""
        self.cards, self.style, self.total = cards, style, total

    @staticmethod
    def _card_alpha(t, t0, t1):
        if t < t0 or t > t1:
            return 0.0
        return min(1.0, (t - t0) / FADE, (t1 - t) / FADE)

    def state(self, t):
        """What is visible at time t – a hashable description (used to skip identical frames)."""
        ops = []
        for ci, c in enumerate(self.cards):
            ca = round(self._card_alpha(t, *c["window"]), 2)
            if ca <= 0:
                continue
            ops.append((ci, "base", -1, ca, 1.0))
            for k, (ws, we) in enumerate(c["words"]):
                if self.style == "write":
                    dur = min(1.4, max(0.22, we - ws))
                    p = round(min(1.0, (t - ws + 0.06) / dur), 2)
                    if p > 0:
                        ops.append((ci, "white", k, ca, p))
                elif self.style == "highlight":
                    if ws - 0.04 <= t < we + 0.04:
                        ops.append((ci, "gold", k, ca, 1.0))
                    elif t >= we + 0.04:
                        ops.append((ci, "white", k, ca, 1.0))
        return tuple(ops)

    def render(self, ops, W, H):
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for ci, kind, k, ca, p in ops:
            card = self.cards[ci]["card"]
            if kind == "base":
                canvas.alpha_composite(card["base"] if ca >= 1 else _scaled(card["base"], ca))
                continue
            sprite, x, y = card[kind][k]
            if p < 1:
                img = _scaled(sprite, _wipe_mask(sprite.width, p) * ca)
            elif ca < 1:
                img = _scaled(sprite, ca)
            else:
                img = sprite
            canvas.alpha_composite(img, dest=(x, y))
        return canvas


def compose(*, background, timeline, audio, total, dest, W=1080, H=1920, fps=30, darken=0.3):
    n_frames = int(round(total * fps))
    bw, bh = int(W * 1.12) // 2 * 2, int(H * 1.12) // 2 * 2
    fc = (
        f"[0:v]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},fps={fps},setsar=1,"
        f"trim=duration={total:.3f},setpts=PTS-STARTPTS,"
        f"crop={W}:{H}:x='(iw-ow)/2*(1+0.8*sin(2*PI*t/{total*1.6:.2f}))':y='(ih-oh)*t/{total:.2f}',"
        f"eq=saturation=1.08,drawbox=x=0:y=0:w=iw:h=ih:color=black@{darken}:t=fill,vignette=PI/4.5[bg];"
        f"[1:v]format=rgba,setpts=PTS-STARTPTS[ov];"
        f"[bg][ov]overlay=0:0:format=auto:shortest=1,"
        f"fade=t=in:st=0:d=0.6,fade=t=out:st={total-0.9:.2f}:d=0.9,format=yuv420p[vout]"
    )
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-stream_loop", "-1", "-i", str(background),
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps), "-i", "pipe:0",
           "-i", str(audio),
           "-filter_complex", fc, "-map", "[vout]", "-map", "2:a",
           "-t", f"{total:.3f}", "-r", str(fps),
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-maxrate", "12M", "-bufsize", "24M", "-profile:v", "high", "-level", "4.1",
           "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(dest)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    last_key, last_bytes = None, None
    try:
        for i in range(n_frames):
            key = timeline.state(i / fps)
            if key != last_key:
                last_bytes, last_key = timeline.render(key, W, H).tobytes(), key
            proc.stdin.write(last_bytes)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed:\n{err[-3000:]}")
    return Path(dest)
