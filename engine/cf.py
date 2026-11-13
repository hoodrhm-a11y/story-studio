"""Cloudflare Workers AI client (images + text)."""
import base64, json, os, time
import requests

ACCOUNT = os.environ.get("CF_ACCOUNT_ID") or ""
TOKEN = os.environ.get("CF_API_TOKEN") or "proxy-injected"


class DailyLimit(Exception):
    """The account's free daily Workers AI allowance is used up."""


def _url(model):
    if not ACCOUNT:
        raise SystemExit("Set CF_ACCOUNT_ID (Cloudflare account id).")
    return f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/{model}"


def _check(r):
    try:
        d = r.json()
    except ValueError:
        r.raise_for_status()
        raise
    if not d.get("success", True) or r.status_code >= 400:
        msg = json.dumps(d.get("errors") or d)[:500]
        if "daily free allocation" in msg:
            raise DailyLimit(msg)
        raise RuntimeError(f"Workers AI error {r.status_code}: {msg}")
    return d["result"]


def _retry(fn, tries=3):
    for i in range(tries):
        try:
            return fn()
        except (requests.RequestException, RuntimeError) as e:
            if i == tries - 1:
                raise
            print(f"  retry after error: {e}")
            time.sleep(4 * (i + 1))


def chat_json(system, user, model="@cf/openai/gpt-oss-120b", max_tokens=6000):
    """Ask a text model for a JSON object and return it parsed."""
    def go():
        r = requests.post(_url(model), headers={"Authorization": f"Bearer {TOKEN}"}, timeout=300, json={
            "instructions": system, "input": user, "max_output_tokens": max_tokens,
            "reasoning": {"effort": "medium"},
        })
        res = _check(r)
        text = ""
        for item in res.get("output", []):
            for c in item.get("content", []) or []:
                if c.get("type") in ("output_text", "text"):
                    text += c.get("text", "")
        if not text:
            text = res.get("response") or res.get("output_text") or ""
        s, e = text.find("{"), text.rfind("}")
        if s < 0 or e < 0:
            raise RuntimeError(f"model returned no JSON: {text[:300]}")
        return json.loads(text[s:e + 1])
    return _retry(go)


def image(out_path, prompt, width, height, refs=(), model="@cf/black-forest-labs/flux-2-dev", steps=28):
    """Generate one image (optionally conditioned on reference images) and save it as PNG."""
    def go():
        files = {"prompt": (None, prompt), "width": (None, str(width)), "height": (None, str(height)),
                 "steps": (None, str(steps))}
        handles = []
        for i, ref in enumerate(refs):
            h = open(ref, "rb"); handles.append(h)
            files[f"input_image_{i}"] = (os.path.basename(ref), h, "image/png")
        try:
            r = requests.post(_url(model), headers={"Authorization": f"Bearer {TOKEN}"}, files=files, timeout=300)
        finally:
            for h in handles:
                h.close()
        res = _check(r)
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(res["image"]))
    _retry(go)
