"""Turn a pasted story into a video plan: narration lines, a cast designed for the story, and scenes."""
import json
from . import cf

SYSTEM = """You are the director of a faceless YouTube story channel. You turn a story into a plan for a narrated,
illustrated video. Reply with ONE JSON object only, no prose, using exactly this shape:

{
  "title": "short catchy video title",
  "characters": [
    {"id": "lowercase_id", "name": "Name", "role": "who they are in the story",
     "look": "clothing, colours, accessories, props and any hat/glasses/hairpiece that fit THIS character and story"}
  ],
  "lines": [
    {"text": "narration line", "pause": 0.3}
  ],
  "scenes": [
    {"first_line": 0, "last_line": 1, "characters": ["lowercase_id"],
     "shot": "what the picture shows: place, time of day, action, framing (wide / medium / close-up), mood, lighting",
     "move": "push_in | pull_out | pan_left | pan_right | rise | fall",
     "fx": []}
  ],
  "emphasis": ["a few single words to colour red in captions"]
}

Rules:
- Narration is first person or third person exactly as the story is told. Keep the story's events and twist. Make it
  gripping: strong first-line hook, short punchy sentences, natural spoken English, no headings, no emojis.
- Each line is one breath: 1 or 2 short sentences, 4 to 22 words. Never split a sentence across lines. Do not use "...".
- pause is the silence after the line in seconds: 0.2 normal, 0.35 before a reveal or dramatic beat, 0.5 at most.
- The final line ends the story (or a cliffhanger) and may invite viewers to follow for part two if the story is unfinished.
- Characters: design a distinct, story-appropriate look for every person who appears (a nurse wears scrubs, a grandma
  a cardigan and glasses, a cop a uniform). Do NOT give everyone a hoodie or a cap. Never describe faces, skin, hair or
  body shape: the base figure is fixed by the art style. Max 6 characters.
- Scenes: cover every line exactly once, in order, with no gaps or overlaps (scene N+1 first_line = scene N last_line + 1).
  One scene per 5 to 8 seconds of narration (about 15 to 25 words). Vary framing between wide, medium and close-up.
  List only characters visible in the shot. Describe the shot concretely so an illustrator can draw it without the
  story. No text, signs, letters or speech bubbles in the picture.
- fx may contain "shake" (impact, fear, sudden noise) and/or "flash" (shock reveal). Use them rarely, max one in four scenes.
"""


def make_plan(story, minutes=1.5, extra=""):
    words = int(minutes * 60 * 2.7)
    user = (f"Target length: about {minutes} minutes of narration, roughly {words} words in total "
            f"(shorten or expand the telling to fit, keep the plot).\n{extra}\n\nSTORY:\n{story.strip()}")
    plan = cf.chat_json(SYSTEM, user)
    return validate(plan)


def validate(plan):
    lines = plan["lines"]
    for ln in lines:
        ln["text"] = ln["text"].replace("...", ",").strip()
        ln["pause"] = max(0.12, min(0.6, float(ln.get("pause", 0.25))))
    ids = {c["id"] for c in plan["characters"]}
    fixed, nxt = [], 0
    for sc in plan["scenes"]:
        a, b = int(sc["first_line"]), int(sc["last_line"])
        a = nxt
        b = max(a, min(b, len(lines) - 1))
        sc["first_line"], sc["last_line"] = a, b
        sc["characters"] = [c for c in sc.get("characters", []) if c in ids]
        sc["move"] = sc.get("move") if sc.get("move") in ("push_in", "pull_out", "pan_left", "pan_right", "rise", "fall") else "push_in"
        sc["fx"] = [f for f in sc.get("fx", []) if f in ("shake", "flash")]
        fixed.append(sc)
        nxt = b + 1
        if nxt >= len(lines):
            break
    if nxt < len(lines):
        fixed[-1]["last_line"] = len(lines) - 1
    plan["scenes"] = fixed
    plan["emphasis"] = [w.lower().strip(".,!?") for w in plan.get("emphasis", [])][:8]
    return plan


if __name__ == "__main__":
    import sys
    print(json.dumps(make_plan(open(sys.argv[1]).read(), float(sys.argv[2]) if len(sys.argv) > 2 else 1.5), indent=2))
