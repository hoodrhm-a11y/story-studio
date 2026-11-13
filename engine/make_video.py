"""Story text in, finished video(s) out.

    python -m engine.make_video story.txt --minutes 1.5 --style dark-cartoon --voice young-narrator \
        --formats vertical,horizontal --out jobs/my-story

Every step is cached in the job folder, so re-running after a failure (or after the daily AI limit resets)
continues where it stopped and never pays for the same image twice.
"""
import argparse, json, os, sys
from . import plan as planner, voice, images, render, cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    return json.load(open(os.path.join(ROOT, "presets", name)))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=1.5)
    ap.add_argument("--style", default="dark-cartoon")
    ap.add_argument("--voice", default="young-narrator")
    ap.add_argument("--formats", default="vertical")
    ap.add_argument("--no-captions", action="store_true")
    a = ap.parse_args(argv)

    os.makedirs(a.out, exist_ok=True)
    style, vp = load("styles.json")[a.style], load("voices.json")[a.voice]
    plan_path = os.path.join(a.out, "plan.json")
    try:
        if os.path.exists(plan_path):
            p = json.load(open(plan_path))
        else:
            print("1/4 planning story")
            p = planner.make_plan(open(a.story).read(), a.minutes)
            json.dump(p, open(plan_path, "w"), indent=2)
        print(f"   {p['title']}: {len(p['lines'])} lines, {len(p['scenes'])} scenes, {len(p['characters'])} characters")

        print("2/4 voice")
        vdir = os.path.join(a.out, "voice"); os.makedirs(vdir, exist_ok=True)
        durs = voice.speak(p["lines"], vp, vdir)
        p["total"] = render.timeline(p, durs)
        print(f"   {p['total']:.1f} s of video")

        print("3/4 pictures")
        idir = os.path.join(a.out, "images"); os.makedirs(idir, exist_ok=True)
        sheets = images.character_sheets(p, style, idir) if p["characters"] else {}
        outs = []
        for fmt in a.formats.split(","):
            imgs = images.scene_images(p, style, sheets, fmt, idir)
            print(f"4/4 rendering {fmt}")
            out = os.path.join(a.out, f"video_{fmt}.mp4")
            render.render(p, imgs, vdir, out, fmt, captions=not a.no_captions)
            outs.append(out)
        json.dump(p, open(os.path.join(a.out, "timeline.json"), "w"), indent=2)
        print("done:", *outs)
    except cf.DailyLimit:
        print("STOPPED: Cloudflare's free daily AI allowance is used up. Re-run after it resets (00:00 UTC) "
              "or enable Workers Paid; finished steps are kept.")
        sys.exit(3)


if __name__ == "__main__":
    main()
