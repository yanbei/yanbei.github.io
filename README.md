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
- Edit `scripts/update_arxiv.py` to change categories, keywords, and ranking

## Local test

```bash
python3 scripts/update_arxiv.py
python3 -m http.server
```

Then open <http://localhost:8000/arxiv.html>
