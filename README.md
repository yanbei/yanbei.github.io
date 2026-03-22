# Research website starter

This repo is a GitHub Pages starter for a personal research website with an automated arXiv watch page.

## Included

- Static website pages: Home, Research, Group, Alumni, Publications, Contact
- `arxiv.html` to display relevant new arXiv papers
- `scripts/update_arxiv.py` to fetch and rank papers from:
  - `gr-qc`
  - `hep-th`
  - `astro-ph.HE`
- GitHub Actions workflow at `.github/workflows/update-arxiv.yml` that runs every 6 hours

## How to publish on GitHub Pages

1. Create a GitHub repo, ideally named `yourusername.github.io`
2. Copy these files into it
3. Push to GitHub
4. In GitHub repo settings, enable **Pages** from the `main` branch `/root`

## How to customize

- Edit `index.html` and the other `.html` files with your content
- Edit `style.css` for the look
- Edit `config/preferences.json` to encode your taste
- Edit `scripts/update_arxiv.py` to change categories, keywords, ranking, and synthesis behavior

## Archive and reuse

Processed papers are archived one-file-per-paper under `data/archive/` and reused on future runs so the pipeline does not redo the same paper unnecessarily.

## OpenAI synthesis

If `OPENAI_API_KEY` is set, the updater will ask OpenAI for summaries. If no key is present, the script falls back to metadata-only summaries.

For GitHub Actions, add `OPENAI_API_KEY` as a repository secret.

## Local test

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai
cp .env.example .env  # optional; then export variables from it
export OPENAI_API_KEY=your_key_here
python3 scripts/update_arxiv.py
python3 -m http.server
```

Then open <http://localhost:8000/arxiv.html>
