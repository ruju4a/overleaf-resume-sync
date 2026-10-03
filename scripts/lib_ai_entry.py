"""Drafts one new LaTeX project entry, matching the formatting of whatever's already
in the Overleaf project's Projects section, and tags it with a tracking comment.

Supports either Anthropic or OpenAI as the backing model - set ai_provider/ai_model
in config.yaml. Whichever you pick, set the matching API key as a GitHub secret:
  anthropic -> ANTHROPIC_API_KEY
  openai    -> OPENAI_API_KEY
"""
import re

_LATEX_SPECIAL_CHARS = {
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}", "\\": r"\textbackslash{}",
}
_LATEX_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _LATEX_SPECIAL_CHARS))


def _latex_escape(text: str) -> str:
    """Escapes LaTeX special chars in plain text pulled straight from GitHub (repo name,
    description, language names). Deterministic - doesn't depend on the AI remembering to
    do this correctly every time, which is what caused compile errors on repo names like
    'NN_cough_dataset' (raw underscores break LaTeX outside math mode)."""
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL_CHARS[m.group()], text)


PROMPT_TEMPLATE = """You are editing a LaTeX resume. Your only job is to produce ONE new project \
entry to append to an existing Projects section.

{style_instruction}

New project info (pulled from its GitHub repo). The Name, Description, and Languages/tech \
values below are ALREADY LaTeX-escaped (special characters like _ and & are already correctly \
backslash-escaped) — use them exactly as given, character for character, do not re-derive them \
from the README or un-escape them:
Name: {name}
Description: {description}
Languages/tech: {languages}
Date for this entry: {date_range}
README excerpt (raw, NOT escaped — this is source material for the bullets only, never copy \
raw text from it directly into your output without escaping any LaTeX special characters \
yourself: _ & % # $ {{ }} ~ ^ \\):
---
{readme}
---

{bullet_instruction}

Requirements:
- Match whatever LaTeX macros/commands/spacing convention the style reference uses. If there is \
no style reference (first project ever added), use a clean, standard, dependency-free format: \
bold title, italic tech stack, right-aligned dates on the same line, then an itemize list of bullets.
- For the date, use EXACTLY this string, verbatim: {date_range}. Do not use any other year or \
date — this is the repo's real creation/activity date, not something to infer from the README.
- Every underscore, ampersand, percent sign, or other LaTeX special character that appears \
ANYWHERE in your output — including inside bullet text you write — must be properly escaped \
(e.g. \\_ not _, \\& not &). This is the single most common way this entry could fail to compile.
- The FIRST line of your output must be exactly this tracking comment: % repo:{repo}
- After that, output ONLY the new entry's LaTeX. No markdown code fences, no explanation, no \
repetition of any existing entries, nothing else.
"""

STYLE_WITH_REFERENCE = """Here is the current content of the Projects section — this defines the \
exact formatting style/macros/structure you must match:
---STYLE REFERENCE START---
{style_block}
---STYLE REFERENCE END---"""

STYLE_WITHOUT_REFERENCE = "The Projects section is currently empty (this is the first entry)."

BULLETS_AUTO = """Write exactly 2 resume bullet points for this project:
- Start each with a strong past-tense action verb (Built, Designed, Implemented, Optimized, etc.)
- Every concrete claim must trace to something actually stated in the README or description —
  a specific technique, file, module, algorithm, library call, or mechanism it names. Do not
  describe generic activity ("facilitated collaboration," "community-driven," "showcased ideas,"
  "streamlined operations") unless the README itself uses that framing — that kind of vague,
  impressive-sounding filler is exactly what makes a bullet unconvincing and inaccurate.
- If the README is thin, sparse, or mostly boilerplate (e.g. just a project name and a generic
  one-line description with no real technical detail), DO NOT pad it into elaborate-sounding
  bullets. Write modest, literal bullets using only what's actually there, even if that means
  the bullets end up short or plain. A short accurate bullet beats a longer invented-sounding one.
- Quantify impact only where the README actually supports a number — never invent one
- No fluff, no first person
- Format each as a separate item using whatever bullet/list macro the style reference uses \
(or \\item in a plain itemize if there's no style reference)"""

BULLETS_MANUAL = """Use exactly these bullet points, verbatim, word for word — do not reword or \
paraphrase them. They are ALREADY LaTeX-escaped — do not add further backslashes or otherwise \
alter the text. Just wrap them in the same LaTeX bullet/list macro the style reference uses:
{bullets_list}"""


def _format_date_range(repo_info: dict) -> str:
    """Turns GitHub's created_at/pushed_at timestamps into a resume-style date string,
    e.g. '2026' if the project was all done in one year, or '2025 -- 2026' if work
    spanned two. Falls back to 'Date unknown' only if GitHub gave us nothing (rare)."""
    created = repo_info.get("created_at")
    pushed = repo_info.get("pushed_at")
    if not created:
        return "Date unknown"

    created_year = created[:4]
    pushed_year = pushed[:4] if pushed else created_year

    if created_year == pushed_year:
        return created_year
    return f"{created_year} -- {pushed_year}"


def _build_prompt(repo_info: dict, style_block: str, override_bullets):
    style_instruction = (
        STYLE_WITH_REFERENCE.format(style_block=style_block.strip())
        if style_block.strip()
        else STYLE_WITHOUT_REFERENCE
    )
    bullet_instruction = (
        BULLETS_MANUAL.format(
            bullets_list="\n".join(f"- {_latex_escape(b)}" for b in override_bullets)
        )
        if override_bullets
        else BULLETS_AUTO
    )
    return PROMPT_TEMPLATE.format(
        style_instruction=style_instruction,
        name=_latex_escape(repo_info.get("name", "")),
        description=_latex_escape(repo_info.get("description", "")),
        languages=_latex_escape(", ".join(repo_info.get("languages", []))),
        date_range=_format_date_range(repo_info),
        readme=repo_info.get("readme", "")[:6000],  # left raw - it's source material, not literal output
        bullet_instruction=bullet_instruction,
        repo=repo_info["repo"],
    )


def _draft_via_anthropic(prompt: str, model: str) -> str:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    response = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def _draft_via_openai(prompt: str, model: str) -> str:
    import openai

    client = openai.OpenAI()  # reads OPENAI_API_KEY from env
    response = client.chat.completions.create(
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def _draft_via_google(prompt: str, model: str) -> str:
    import os

    import requests

    api_key = os.environ["GOOGLE_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    response = requests.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    if response.status_code == 404:
        raise RuntimeError(
            f"Model '{model}' not found by the Gemini API. Model names change often — "
            f"run `curl -s -H \"x-goog-api-key: $GOOGLE_API_KEY\" "
            f"https://generativelanguage.googleapis.com/v1beta/models | grep '\"name\"'` "
            f"to see what's actually available to your key right now, and update ai_model "
            f"in config.yaml to match."
        )
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


_PROVIDERS = {
    "anthropic": _draft_via_anthropic,
    "openai": _draft_via_openai,
    "google": _draft_via_google,
}


def _call_with_retries(fn, prompt: str, model: str, attempts: int = 4):
    """Retries transient failures (503s, rate limits, network blips) with backoff.
    Doesn't special-case error types - a bad API key will also retry, but only wastes
    a few seconds before failing with the real error, which is fine for a once-a-day run."""
    import time

    last_error = None
    for attempt in range(attempts):
        try:
            return fn(prompt, model)
        except Exception as e:
            last_error = e
            if attempt < attempts - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                print(f"    API call failed ({e}), retrying in {wait}s...")
                time.sleep(wait)
    raise last_error


def draft_latex_entry(
    repo_info: dict,
    style_block: str,
    override_bullets: list[str] | None = None,
    provider: str = "anthropic",
    model: str = "claude-sonnet-5",
) -> str:
    if provider not in _PROVIDERS:
        raise ValueError(
            f"Unknown ai_provider '{provider}' in config.yaml — use 'anthropic', 'openai', or 'google'"
        )

    prompt = _build_prompt(repo_info, style_block, override_bullets)
    text = _call_with_retries(_PROVIDERS[provider], prompt, model)
    return text.strip()
