# Auto-Syncing Overleaf Resume

Push a new project to GitHub -> it shows up in your live Overleaf resume automatically,
in the same LaTeX style as everything already there. No project list to maintain, no
generated PDF, no separate template — the pipeline scans your GitHub account and edits
your actual Overleaf document directly.

## How it works, in one sentence

Once a day (or on-demand), the pipeline lists every public repo on your GitHub account,
skips anything already in your resume, and drafts + appends a new entry for anything new.

## One-time setup

**1. Mark your Projects section.** In your Overleaf project, wrap your existing Projects
section with two comment lines:

```latex
\section*{Projects}
% AUTO-PROJECTS-START
\textbf{My Existing Project} $\vert$ \textit{Python, Flask} \hfill 2024 \\
\begin{itemize}[leftmargin=*]
  \item Whatever you already have here.
\end{itemize}
% AUTO-PROJECTS-END
```

Everything between those two lines is what the pipeline reads (to learn your formatting)
and edits. It never touches anything outside them — header, education, experience, skills
are all left alone.

**2. Set `config.yaml`:**
```yaml
main_tex_file: "main.tex"                # your actual resume filename in Overleaf
start_marker: "% AUTO-PROJECTS-START"
end_marker: "% AUTO-PROJECTS-END"
ai_provider: "google"                    # "anthropic", "openai", or "google"
ai_model: "gemini-3-flash"               # match whatever provider you picked
github_username: "yourhandle"            # your real GitHub username
exclude_repos:                           # repo names to never turn into resume entries
  - "dotfiles"
  - "some-course-homework-repo"
```
Model names and prices change often — check the provider's current pricing/model page and
put whatever's current there rather than trusting an old default.

**Which AI provider to pick:** Anthropic and OpenAI are pay-per-use APIs — separate billing
from a Claude Pro or ChatGPT Plus subscription; neither of those subscriptions gives you an
API key. **Google is the one genuinely free option**: a key from aistudio.google.com/apikey
needs no credit card and no billing setup, just a Google account. It's limited to the
"Flash" models with modest rate limits, but for this task (a couple of calls only when a
genuinely new repo shows up) that's plenty. Note a Gemini Pro/AI Pro subscription doesn't
unlock this either — it's the free AI Studio tier itself that's free, independent of any
subscription.

**3. Get your Overleaf git credentials** (paid plan required):
- Account Settings → Git Integration → generate a Git token → this is `OVERLEAF_GIT_TOKEN`
- Your project's URL is `overleaf.com/project/<id>` → that `<id>` is `OVERLEAF_PROJECT_ID`

**4. Get an API key for whichever provider you picked:**
- Google (free): aistudio.google.com/apikey → Create API key → this is `GOOGLE_API_KEY`
- Anthropic (paid): console.anthropic.com → Create Key → this is `ANTHROPIC_API_KEY`
- OpenAI (paid): platform.openai.com → Create Key → this is `OPENAI_API_KEY`

**5. Add GitHub Secrets** (repo Settings → Secrets and variables → Actions):
- `OVERLEAF_PROJECT_ID`
- `OVERLEAF_GIT_TOKEN`
- Whichever key matches your `ai_provider`: `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or
  `OPENAI_API_KEY` — only that one needs a real value, the others can be left unset.

(`GITHUB_TOKEN` is automatic — no setup needed.)

That's it — no `projects.yaml`, nothing to push to trigger it. It runs on its own schedule.

## Adding a new project

Just push the project to a new public repo on your GitHub, like you normally would.
Nothing else. Within a day (or run it manually from the Actions tab if you don't want to
wait), it'll show up as a new entry in your Overleaf resume.

What the pipeline does each run:
1. Clones your Overleaf project via the git bridge
2. Reads the current Projects section between the markers, and notes which repos are
   already represented there (via a hidden `% repo:owner/name` comment per entry)
3. Lists every public repo on your GitHub account, and works out which ones are new —
   skipping forks, anything in `exclude_repos`, and this pipeline's own repo automatically
4. For each new one: pulls its README/description, sends it to whichever AI provider
   you've configured along with your existing entries as a style reference, and gets back
   one new entry in matching format
5. Appends all new entries inside the markers and pushes straight back to Overleaf

## Overriding AI-drafted bullets

Most repos need nothing — bullets are drafted automatically from the README. For a repo
where that's not enough (a competition result, a metric that isn't in the README), add it
to `overrides.yaml`:

```yaml
overrides:
  iam-project:
    bullets:
      - "Placed 2nd out of 300+ teams designing a secure identity and access management system."
      - "Implemented role-based access control and authentication flows under competitive time constraints."
```

The key is just the repo name (not `owner/name`). Still wrapped in matching LaTeX by the AI
— only the wording is fixed, not the formatting.

## Changing the schedule

`.github/workflows/sync-overleaf.yml` runs on a cron schedule (default: once a day). Edit
the `cron:` line to change frequency, or just use the "Run workflow" button on the Actions
tab in GitHub any time you don't want to wait for the schedule.

## Running locally

```bash
pip install pyyaml requests anthropic openai
export OVERLEAF_PROJECT_ID=your_project_id
export OVERLEAF_GIT_TOKEN=your_git_token
export GOOGLE_API_KEY=your_key      # or ANTHROPIC_API_KEY / OPENAI_API_KEY, matching config.yaml
export GITHUB_TOKEN=your_github_pat # recommended locally too, to avoid rate limits
python3 scripts/sync_overleaf.py
```

## How style-matching works

There's no separate template file. Each run, the AI is shown the exact current contents of
your Projects section (LaTeX macros, spacing, everything) and told to produce new entries in
the same style. The very first time you use this — before any auto-entries exist — it's
mimicking whatever hand-written entries you already have. After that, it's also seeing its
own previously-generated entries, so style stays consistent as your resume grows.

## Notes

- This is additive only: it never edits or removes an existing entry, only appends new ones.
  Reordering, trimming, or JD-specific tailoring is still a separate manual (or "ask me") step.
- If a repo's README changes significantly after it's already synced, the pipeline won't
  notice — it only looks at repos with no `% repo:` comment yet. Delete that comment + its
  entry manually in Overleaf if you want it regenerated.
- Runs against public repos only. Private repos aren't picked up (the unauthenticated repo
  list can't see them, and syncing private-repo details into a resume you may share isn't
  something to do silently by default).
