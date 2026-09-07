"""Drafts one new LaTeX project entry, matching the formatting of whatever's already
in the Overleaf project's Projects section, and tags it with a tracking comment.

Supports either Anthropic or OpenAI as the backing model - set ai_provider/ai_model
in config.yaml. Whichever you pick, set the matching API key as a GitHub secret:
  anthropic -> ANTHROPIC_API_KEY
  openai    -> OPENAI_API_KEY
"""
PROMPT_TEMPLATE = """You are editing a LaTeX resume. Your only job is to produce ONE new project \
entry to append to an existing Projects section.

{style_instruction}

New project info (pulled from its GitHub repo):
Name: {name}
Description: {description}
Languages/tech: {languages}
README excerpt:
---
{readme}
---

{bullet_instruction}

Requirements:
- Match whatever LaTeX macros/commands/spacing convention the style reference uses. If there is \
no style reference (first project ever added), use a clean, standard, dependency-free format: \
bold title, italic tech stack, right-aligned dates on the same line, then an itemize list of bullets.
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
- Be specific about what was built and how, using real details from the README
- Quantify impact only where the README actually supports a number — never invent one
- No fluff, no first person
- Format each as a separate item using whatever bullet/list macro the style reference uses \
(or \\item in a plain itemize if there's no style reference)"""

BULLETS_MANUAL = """Use exactly these bullet points, verbatim, word for word — do not reword or \
paraphrase them. Just wrap them in the same LaTeX bullet/list macro the style reference uses:
{bullets_list}"""


def _build_prompt(repo_info: dict, style_block: str, override_bullets):
    style_instruction = (
        STYLE_WITH_REFERENCE.format(style_block=style_block.strip())
        if style_block.strip()
        else STYLE_WITHOUT_REFERENCE
    )
    bullet_instruction = (
        BULLETS_MANUAL.format(bullets_list="\n".join(f"- {b}" for b in override_bullets))
        if override_bullets
        else BULLETS_AUTO
    )
    return PROMPT_TEMPLATE.format(
        style_instruction=style_instruction,
        name=repo_info.get("name", ""),
        description=repo_info.get("description", ""),
        languages=", ".join(repo_info.get("languages", [])),
        readme=repo_info.get("readme", "")[:6000],
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
