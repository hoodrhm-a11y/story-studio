# Story Studio

Paste a story, get a narrated, illustrated HD video for YouTube, Facebook and Instagram.

**Pipeline:** story → plan (AI writes narration lines, designs a cast that fits the story, splits it into scenes)
→ voice (Kokoro, free, on CPU) → character sheet + scene images (FLUX.2 on Cloudflare Workers AI, same characters in
every scene) → render (camera moves, shake/flash, word-by-word captions, grain, dust, ambience, whooshes) → MP4.

The base figure (round white head, dot eyes, stick limbs) and the art style stay the same in every video; clothes and
props are designed per character from the story.

## Make a video (no install)
GitHub → **Actions** → **Make video** → **Run workflow**, paste the story, pick length / style / voice / formats.
When it finishes, the MP4s are under **Artifacts** on the run page.

If it stops because the free daily Cloudflare AI allowance ran out, run it again later with the **same job name**:
finished steps (plan, voice, images) are kept and not paid for twice.

Needs two repository secrets: `CF_ACCOUNT_ID` and `CF_API_TOKEN` (a Workers AI token).

## Run locally
```bash
pip install -r requirements.txt          # plus ffmpeg and the Inter font
export CF_ACCOUNT_ID=... CF_API_TOKEN=...
python -m engine.make_video story.txt --out jobs/my-story --minutes 1.5 --formats vertical,horizontal
```

## Presets
- `presets/styles.json`: art styles (`dark-cartoon`, `bright-cartoon`, `storybook`)
- `presets/voices.json`: narrator voices; `young-narrator` (70% Puck + 30% Eric, speed 1.08) is the default

## Cost (approx.)
Voice and rendering are free. Images: about 1,000 Workers AI neurons (~$0.01) each; Cloudflare's free 10,000
neurons/day covers about 9 images. A 1.5-minute video uses ~15 images.
