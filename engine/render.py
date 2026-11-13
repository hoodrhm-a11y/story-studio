"""Turn scene images + narration into a finished MP4: camera moves, shake/flash, captions, grain, dust and sound."""
import math, os, random, re, subprocess
from multiprocessing import Pool
import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont

FPS = 30
XF = 0.35          # crossfade between scenes (s)
LEAD = 0.5         # silence before the first line (s)
TAIL = 1.0         # hold after the last line (s)
FONT = os.environ.get("CAPTION_FONT", "/usr/share/fonts/opentype/inter/Inter-Black.otf")
FORMATS = {"vertical": (1080, 1920), "horizontal": (1920, 1080)}

MOVES = {  # zoom_from, zoom_to, dx_from, dx_to, dy_from, dy_to (fractions of the image)
    "push_in": (1.00, 1.14, 0, 0, 0, 0), "pull_out": (1.16, 1.02, 0, 0, 0, 0),
    "pan_left": (1.10, 1.12, 0.035, -0.035, 0, 0), "pan_right": (1.10, 1.12, -0.035, 0.035, 0, 0),
    "rise": (1.10, 1.12, 0, 0, 0.035, -0.035), "fall": (1.10, 1.12, 0, 0, -0.035, 0.035),
}


def ease(x):
    x = max(0.0, min(1.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def timeline(plan, durs):
    t = LEAD
    for ln, d in zip(plan["lines"], durs):
        ln["start"], ln["end"] = t, t + d
        t += d + ln["pause"]
    total = plan["lines"][-1]["end"] + TAIL
    sc = plan["scenes"]
    for i, s in enumerate(sc):
        s["start"] = 0.0 if i == 0 else plan["lines"][s["first_line"]]["start"]
    for i, s in enumerate(sc):
        s["end"] = sc[i + 1]["start"] if i + 1 < len(sc) else total
    return total


def word_times(plan):
    words = []
    for ln in plan["lines"]:
        ws = ln["text"].split()
        wt = [len(re.sub(r"\W", "", w)) + 2 + (5 if re.search(r"[.,?!;:]$", w) else 0) for w in ws]
        t, usable = ln["start"] + 0.05, (ln["end"] - ln["start"]) - 0.1
        for w, x in zip(ws, wt):
            d = usable * x / sum(wt)
            words.append((w, t, t + d)); t += d
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) == 3 or re.search(r"[.,?!;:]$", w[0]) or (len(cur) == 2 and len(w[0]) > 7):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    return chunks


# ---------------------------------------------------------------- per-process state for the frame workers
G = {}


def _init(job):
    W, H = job["size"]
    random.seed(7)
    imgs = []
    for p in job["images"]:
        im = Image.open(p).convert("RGB")
        s = max(W / im.width, H / im.height) * 1.22
        imgs.append(im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS))
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    G.update(job, imgs=imgs, W=W, H=H,
             vig=np.clip(1.0 - 0.55 * np.clip(r - 0.55, 0, 1) ** 1.5, 0, 1)[..., None].astype(np.float32),
             grain=[np.random.default_rng(i).normal(0, 4, (H // 2, W // 2, 1)).repeat(2, 0).repeat(2, 1).astype(np.float32) for i in range(6)],
             dust=[[random.uniform(0, W), random.uniform(0, H), random.uniform(1.5, 4) * W / 1080, random.uniform(-12, 12),
                    random.uniform(-30, -8), random.uniform(0.2, 0.6)] for _ in range(60)],
             font_px=92 if H > W else 76)


def _scene(k, t):
    sc, im, W, H = G["scenes"][k], G["imgs"][k], G["W"], G["H"]
    span = sc["end"] - sc["start"] + XF
    p = ease(t / span)
    z0, z1, x0, x1, y0, y1 = MOVES[sc["move"]]
    z = z0 + (z1 - z0) * p
    cx = im.width / 2 + (x0 + (x1 - x0) * p) * im.width
    cy = im.height / 2 + (y0 + (y1 - y0) * p) * im.height
    base = min(im.width / W, im.height / H)
    sw, sh = W * base / z, H * base / z
    rng = random.Random(int(t * 1000) + k)
    dx = math.sin(t * 1.3 + k) * 4 + math.sin(t * 2.1) * 2
    dy = math.cos(t * 1.1 + k) * 4
    if "shake" in sc["fx"] and t < 0.6:
        a = (0.6 - t) / 0.6
        dx += rng.uniform(-1, 1) * 28 * a; dy += rng.uniform(-1, 1) * 28 * a
    left = max(0, min(im.width - sw, cx - sw / 2 + dx)); top = max(0, min(im.height - sh, cy - sh / 2 + dy))
    return im.transform((W, H), Image.AFFINE, (sw / W, 0, left, 0, sh / H, top), resample=Image.BICUBIC)


def _caption(img, t):
    W, H = G["W"], G["H"]
    for ch in G["chunks"]:
        if ch[0][1] - 0.05 <= t < ch[-1][2] + 0.12:
            break
    else:
        return
    pop = min(1, (t - ch[0][1] + 0.05) / 0.12)
    sc = 0.85 + 0.15 * (1 - (1 - pop) ** 3)
    f = ImageFont.truetype(FONT, int(G["font_px"] * sc))
    texts = [w[0].upper() for w in ch]
    space = f.getlength(" ")
    widths = [f.getlength(s) for s in texts]
    rows, row, rw = [], [], 0
    for i, wdt in enumerate(widths):
        if row and rw + space + wdt > W * 0.86:
            rows.append(row); row, rw = [], 0
        row.append(i); rw += (space if len(row) > 1 else 0) + wdt
    rows.append(row)
    d = ImageDraw.Draw(img)
    lh = int(G["font_px"] * 1.17 * sc)
    y = int(H * (0.77 if H > W else 0.80)) - len(rows) * lh // 2
    stroke = max(4, G["font_px"] // 10)
    for row in rows:
        x = (W - (sum(widths[i] for i in row) + space * (len(row) - 1))) / 2
        for i in row:
            w = ch[i]
            key = re.sub(r"[^\w]", "", w[0].lower())
            col = (255, 214, 0) if w[1] <= t < w[2] else ((255, 80, 60) if key in G["emphasis"] and t >= w[1] else (255, 255, 255))
            d.text((x + 4, y + 7), texts[i], font=f, fill=(0, 0, 0))
            d.text((x, y), texts[i], font=f, fill=col, stroke_width=stroke, stroke_fill=(0, 0, 0))
            x += widths[i] + space
        y += lh


def _frame(n):
    t = n / FPS
    scenes = G["scenes"]
    k = max(i for i, s in enumerate(scenes) if i == 0 or s["start"] <= t)
    lt = t - scenes[k]["start"]
    img = _scene(k, lt)
    if k > 0 and lt < XF:
        img = Image.blend(_scene(k - 1, t - scenes[k - 1]["start"]), img, ease(lt / XF))
    a = np.asarray(img).astype(np.float32)
    if "flash" in scenes[k]["fx"] and lt < 0.15:
        a = a + (255 - a) * (0.7 * (1 - lt / 0.15))
    a = a * G["vig"] + G["grain"][n % 6]
    T = G["total"]
    if t < 0.4: a *= t / 0.4
    if t > T - 0.6: a *= max(0, (T - t) / 0.6)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img, "RGBA")
    W, H = G["W"], G["H"]
    for p in G["dust"]:
        x = (p[0] + p[3] * t) % W; y = (p[1] + p[4] * t) % H
        d.ellipse((x - p[2], y - p[2], x + p[2], y + p[2]), fill=(255, 235, 200, int(255 * p[5] * (0.6 + 0.4 * math.sin(t * 2 + p[0])))))
    if G["captions"]:
        _caption(img, t)
    return img.tobytes()


def _audio(plan, voice_dir, total, out):
    sr = sf.info(os.path.join(voice_dir, "line_000.wav")).samplerate
    mix = np.zeros(int((total + 0.5) * sr), dtype=np.float32)
    for i, ln in enumerate(plan["lines"]):
        a, _ = sf.read(os.path.join(voice_dir, f"line_{i:03d}.wav"), dtype="float32")
        s = int(ln["start"] * sr); mix[s:s + len(a)] += a[: len(mix) - s]
    nar = out + ".narration.wav"
    sf.write(nar, mix, sr)
    inputs = ["-i", nar, "-f", "lavfi", "-t", f"{total}", "-i", "anoisesrc=color=brown:amplitude=0.5",
              "-f", "lavfi", "-t", f"{total}", "-i", "sine=f=49:sample_rate=44100"]
    filt = ["[0:a]highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=80,equalizer=f=3000:t=q:w=1:g=2,volume=1.5[v]",
            f"[1:a]lowpass=f=300,volume=0.09,afade=t=in:d=1.5,afade=t=out:st={total - 1.2}:d=1.2[amb]",
            f"[2:a]volume=0.08,tremolo=f=0.25:d=0.6,afade=t=in:d=2,afade=t=out:st={total - 1.2}:d=1.2[drone]"]
    tags, n = [], 3
    for k, sc in enumerate(plan["scenes"][1:], 1):
        ms = int(max(0, sc["start"] - 0.3) * 1000)
        inputs += ["-f", "lavfi", "-t", "0.6", "-i", "anoisesrc=color=pink:amplitude=0.8"]
        filt.append(f"[{n}:a]highpass=f=600,lowpass=f=3500,afade=t=in:d=0.3,afade=t=out:st=0.3:d=0.3,volume=0.25,adelay={ms}|{ms}[w{k}]")
        tags.append(f"[w{k}]"); n += 1
        if sc["fx"]:
            ms = int(sc["start"] * 1000)
            inputs += ["-f", "lavfi", "-t", "1.2", "-i", "sine=f=55:sample_rate=44100"]
            filt.append(f"[{n}:a]afade=t=out:st=0:d=1.2,volume=1.3,adelay={ms}|{ms}[b{k}]")
            tags.append(f"[b{k}]"); n += 1
    filt.append(f"[v][amb][drone]{''.join(tags)}amix=inputs={3 + len(tags)}:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[aout]")
    wav = out + ".audio.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt), "-map", "[aout]",
                    "-t", f"{total}", "-ar", "44100", wav], check=True)
    os.remove(nar)
    return wav


def render(plan, images, voice_dir, out, fmt="vertical", captions=True, workers=None):
    total = plan["total"]
    W, H = FORMATS[fmt]
    job = {"size": (W, H), "images": images, "scenes": plan["scenes"], "chunks": word_times(plan),
           "emphasis": set(plan.get("emphasis", [])), "total": total, "captions": captions}
    wav = _audio(plan, voice_dir, total, out)
    nf = int(total * FPS)
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                           "-maxrate", "14M", "-bufsize", "28M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                           "-movflags", "+faststart", "-shortest", out], stdin=subprocess.PIPE)
    with Pool(workers or os.cpu_count(), initializer=_init, initargs=(job,)) as pool:
        for i, buf in enumerate(pool.imap(_frame, range(nf), chunksize=8)):
            ff.stdin.write(buf)
            if i % 300 == 0:
                print(f"  frame {i}/{nf}", flush=True)
    ff.stdin.close(); ff.wait()
    os.remove(wav)
    if ff.returncode:
        raise RuntimeError("ffmpeg failed")
    return out
