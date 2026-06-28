(() => {
  const dataEl = document.getElementById('guide-material-data');
  if (!dataEl) return;
  const materials = JSON.parse(dataEl.textContent);
  const selected = new Set(['general']);
  const requirements = document.getElementById('guide-requirements');
  const state = document.getElementById('guide-state');
  const results = document.getElementById('guide-results');
  const heading = document.getElementById('guide-heading');
  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const value = (material, key) => Number((material.scores?.[state.value] || material.scores?.dry || {})[key] ?? 0);
  const maxScore = (materials) => Math.max(...materials.map((r) => r.rank), 1);
  const metric = (material, keys) => keys.reduce((sum, [key, weight]) => sum + value(material, key) * weight, 0);
  const scoring = {
    general: (m) => metric(m, [['printability',1.1],['strength_xy',.8],['impact_resistance',.6],['water_resistance',.4]]) - value(m,'price_range')*.12,
    outdoor: (m) => metric(m, [['uv_resistance',1.2],['water_resistance',.8],['heat_resistance',.7]]),
    flexible: (m) => metric(m, [['impact_resistance',.8],['layer_adhesion',.4]]) + (m.family === 'Elastomer' ? 14 : 0) - value(m,'rigidity_xy')*.35,
    heat: (m) => metric(m, [['heat_resistance',1.3],['creep_resistance',.45]]) + Math.min(Number(m.properties?.hdt_c || 0)/45, 5),
    stiff: (m) => metric(m, [['rigidity_xy',1.3],['strength_xy',.7],['creep_resistance',.45]]),
    impact: (m) => metric(m, [['impact_resistance',1.25],['layer_adhesion',.85],['strength_xy',.2]]),
    chemical: (m) => metric(m, [['chemical_resistance',1.1],['water_resistance',.9],['moisture_tolerance',.35]]),
    cheap: (m) => metric(m, [['printability',.8],['strength_xy',.3]]) + (11-value(m,'price_range'))*1.25,
  };
  const why = (m, needs) => {
    const notes=[];
    if (needs.has('heat')) notes.push(`heat ${value(m,'heat_resistance')}/10`);
    if (needs.has('stiff')) notes.push(`XY rigidity ${value(m,'rigidity_xy')}/10`);
    if (needs.has('impact')) notes.push(`impact ${value(m,'impact_resistance')}/10`);
    if (needs.has('outdoor')) notes.push(`UV ${value(m,'uv_resistance')}/10`);
    if (needs.has('chemical')) notes.push(`water ${value(m,'water_resistance')}/10`);
    if (needs.has('cheap')) notes.push(`price range ${value(m,'price_range')}/10`);
    if (needs.has('flexible')) notes.push(m.family === 'Elastomer' ? 'elastomer family' : `impact ${value(m,'impact_resistance')}/10`);
    if (!notes.length) notes.push(`printability ${value(m,'printability')}/10`);
    return notes.slice(0,3).join(' · ');
  };
  const render = () => {
    const ranked = materials.map((material) => ({...material, rank:[...selected].reduce((sum, need) => sum + scoring[need](material),0)})).sort((a,b)=>b.rank-a.rank).slice(0,6);
    const top = maxScore(ranked);
    heading.textContent = `${ranked.length} materials ranked for ${[...selected].join(' + ')}.`;
    results.innerHTML = ranked.map((m, index) => {
      const pct = Math.max(8, m.rank / top * 100);
      const caution = Number(m.properties?.moisture_sensitivity || 0) >= 8 ? 'Drying discipline required' : (value(m,'impact_resistance') <= 3 ? 'Stiff, but not impact-first' : 'Balanced within selected constraints');
      return `<a class="guide-result" style="--material-color:${esc(m.family_color)}" href="/materials/${esc(m.slug)}"><div class="guide-rank">${index+1}</div><div class="guide-result-main"><div class="material-card-top"><span class="family-pill">${esc(m.family)}</span><span class="subfamily-pill">${esc(m.subfamily)}</span></div><h3>${esc(m.name)}</h3><p>${esc(m.best_for)}</p><div class="guide-bar"><i style="width:${pct}%"></i></div><small>Why it ranked: ${esc(why(m, selected))}</small></div><div class="guide-caution"><b>${Number(m.properties?.hdt_c || 0) || '—'} °C HDT</b><span>${esc(caution)}</span></div><strong class="guide-arrow">→</strong></a>`;
    }).join('');
  };
  requirements.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-need]');
    if (!button) return;
    const need = button.dataset.need;
    if (selected.has(need) && selected.size > 1) selected.delete(need); else selected.add(need);
    requirements.querySelectorAll('button').forEach((candidate) => candidate.classList.toggle('is-selected', selected.has(candidate.dataset.need)));
  });
  document.getElementById('guide-run').addEventListener('click', render);
  state.addEventListener('change', render);
  requirements.querySelectorAll('button').forEach((button) => button.classList.toggle('is-selected', selected.has(button.dataset.need)));
  render();
})();
