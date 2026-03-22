---
layout: default
title: arXiv Archive
permalink: /arxiv-archive/
---

<h2>arXiv Archive</h2>
<p class="page-intro">Archived featured papers are grouped by month. This page is generated from <code>data/archive_index.json</code>.</p>
<div id="archive-status" class="card">Loading archive…</div>
<div id="archive-months"></div>

<script>
  async function loadArchive() {
    const status = document.getElementById('archive-status');
    const monthsEl = document.getElementById('archive-months');
    try {
      const res = await fetch('{{ '/data/archive_index.json' | relative_url }}', { cache: 'no-store' });
      const data = await res.json();
      const months = data.months || [];
      status.innerHTML = `<strong>Months in archive:</strong> ${months.length}<br><strong>Total papers:</strong> ${months.reduce((n, m) => n + (m.count || 0), 0)}`;
      monthsEl.innerHTML = months.map(month => `
        <section>
          <h3>${month.month} <span class="archive-count">(${month.count})</span></h3>
          <div class="paper-list">
            ${month.papers.map(p => `
              <article class="paper">
                <div class="paper-meta">${p.category} · <a href="https://arxiv.org/abs/${p.id}" target="_blank" rel="noopener">${p.id}</a> · <span class="score">Relevance ${p.relevance}/5</span>${p.used_openai ? ' · <span class="mini-badge badge-openai">OpenAI</span>' : ' · <span class="mini-badge badge-fallback">Metadata fallback</span>'}${p.used_pdf_text ? ' · <span class="mini-badge badge-pdf">PDF-read</span>' : ''}${p.worth_reading_full ? ' · <strong>Worth reading in full</strong>' : ''}</div>
                <h4>${p.title}</h4>
                <p><strong>Authors:</strong> ${(p.authors || []).slice(0, 3).join(', ')}${(p.authors || []).length > 3 ? `, et al. (${p.authors.length} authors)` : ''}</p>
                <ul>
                  ${(p.summary_bullets || []).map(b => `<li>${b}</li>`).join('')}
                </ul>
              </article>
            `).join('')}
          </div>
        </section>
      `).join('');
    } catch (err) {
      status.textContent = 'Could not load the archive yet.';
    }
  }
  loadArchive();
</script>
