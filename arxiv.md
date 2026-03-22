---
layout: default
title: arXiv Watch
permalink: /arxiv/
---

<h2>Relevant new arXiv papers</h2>
<p class="page-intro">This page is generated from <code>data/arxiv.json</code>. It supports multiple watchlists, shorter author lists, and tabbed navigation.</p>
<div id="status" class="card">Loading papers…</div>
<div id="watches"></div>

<script src="{{ '/data/arxiv.js' | relative_url }}"></script>
<script>
  function renderWatchPanel(w) {
    return `
      <section class="tab-panel" data-watch-panel="${w.id}">
        <p class="page-intro"><strong>Categories:</strong> ${w.categories.join(', ')}</p>
        <div class="paper-list">
          ${w.papers.map(p => `
            <article class="paper">
              <div class="paper-meta">${p.category} · <a href="https://arxiv.org/abs/${p.id}" target="_blank" rel="noopener">${p.id}</a> · <span class="score">Relevance ${p.relevance}/5</span>${p.worth_reading_full ? ' · <strong>Worth reading in full</strong>' : ''}</div>
              <h3>${p.title}</h3>
              <p><strong>Authors:</strong> ${(p.authors_short || p.authors).join(', ')}</p>
              <ul>
                ${(p.summary_bullets || []).map(b => `<li>${b}</li>`).join('')}
              </ul>
            </article>
          `).join('')}
        </div>
      </section>
    `;
  }

  function activateTab(watchId) {
    const buttons = document.querySelectorAll('[data-watch-tab]');
    const panels = document.querySelectorAll('[data-watch-panel]');
    buttons.forEach(btn => {
      const active = btn.getAttribute('data-watch-tab') === watchId;
      btn.classList.toggle('active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
    });
    panels.forEach(panel => {
      panel.style.display = panel.getAttribute('data-watch-panel') === watchId ? 'block' : 'none';
    });
  }

  async function loadPapers() {
    const status = document.getElementById('status');
    const watches = document.getElementById('watches');
    try {
      let data = window.ARXIV_DATA;
      if (!data) {
        const res = await fetch('{{ '/data/arxiv.json' | relative_url }}', { cache: 'no-store' });
        data = await res.json();
      }
      const display = data.display || {};
      const papersPerWatch = typeof display.top_n !== 'undefined' ? display.top_n : 'unknown';
      const maxAuthors = typeof display.max_authors !== 'undefined' ? display.max_authors : 'unknown';
      status.innerHTML = `<strong>Last updated:</strong> ${data.updated || 'unknown'}<br><strong>OpenAI synthesis:</strong> ${data.openai_enabled ? 'enabled' : 'metadata-only fallback'}<br><strong>Papers per watch:</strong> ${papersPerWatch}<br><strong>Displayed authors:</strong> first ${maxAuthors}`;

      const watchList = data.watches || [];
      if (!watchList.length) {
        watches.innerHTML = '<div class="card">No watchlists found.</div>';
        return;
      }

      const tabButtons = watchList.map((w, index) => `
        <button class="tab-button${index === 0 ? ' active' : ''}" data-watch-tab="${w.id}" aria-selected="${index === 0 ? 'true' : 'false'}">${w.label}</button>
      `).join('');
      const tabPanels = watchList.map(renderWatchPanel).join('');

      watches.innerHTML = `
        <div class="tabs" role="tablist">${tabButtons}</div>
        <div class="tab-panels">${tabPanels}</div>
      `;

      document.querySelectorAll('[data-watch-tab]').forEach(btn => {
        btn.addEventListener('click', () => activateTab(btn.getAttribute('data-watch-tab')));
      });

      activateTab(watchList[0].id);
    } catch (err) {
      status.textContent = 'Could not load arXiv data yet. Run the updater locally or via GitHub Actions after publishing the repo.';
    }
  }
  loadPapers();
</script>
