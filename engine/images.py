"""Character sheets and scene images, drawn in one fixed style with story-specific characters."""
import os
from . import cf

SIZES = {"vertical": (768, 1344), "horizontal": (1344, 768)}


def _sheet_groups(chars, size=3):
    return [chars[i:i + size] for i in range(0, len(chars), size)]


def character_sheets(plan, style, out_dir):
    """One reference sheet per group of up to 3 characters. Returns {char_id: sheet_path}."""
    where = {}
    for g, group in enumerate(_sheet_groups(plan["characters"])):
        path = os.path.join(out_dir, f"cast_{g}.png")
        people = " ".join(f"{['LEFT', 'MIDDLE', 'RIGHT'][i] if len(group) == 3 else ['LEFT', 'RIGHT'][i] if len(group) == 2 else 'CENTRE'}: "
                          f"{c['name'].upper()}, {c['look']}." for i, c in enumerate(group))
        prompt = (f"Character reference sheet: {len(group)} character(s) standing side by side, full body, front view, "
                  f"neutral pose, plain dark grey background, even lighting. {people} {style['base_figure']} {style['art']}")
        if not os.path.exists(path):
            print("  drawing cast sheet", g + 1)
            cf.image(path, prompt, 1344, 768)
        for c in group:
            where[c["id"]] = path
    return where


def scene_images(plan, style, sheets, fmt, out_dir):
    w, h = SIZES[fmt]
    chars = {c["id"]: c for c in plan["characters"]}
    paths = []
    for i, sc in enumerate(plan["scenes"]):
        path = os.path.join(out_dir, f"scene_{i:02d}_{fmt}.png")
        paths.append(path)
        if os.path.exists(path):
            continue
        present = [chars[c] for c in sc["characters"]]
        refs = sorted({sheets[c["id"]] for c in present})[:3]
        if present:
            who = ("Use the exact characters from the reference image(s), same clothes and colours: " +
                   "; ".join(f"{c['name'].upper()} ({c['look']})" for c in present) +
                   f". Only these {len(present)} character(s) appear, each exactly once; ignore any other character on the sheet. ")
        else:
            who = "No people in this shot. "
        prompt = (f"{'Vertical' if fmt == 'vertical' else 'Wide horizontal'} cinematic illustration. {who}"
                  f"{sc['shot']} {style['base_figure'] if present else ''} {style['art']}")
        print(f"  drawing scene {i + 1}/{len(plan['scenes'])}")
        cf.image(path, prompt, w, h, refs=refs)
    return paths
