(() => {
  const dataEl = document.getElementById('guide-material-data');
  if (!dataEl) return;

  const materials = JSON.parse(dataEl.textContent);
  const selected = new Set(['general']);
  const requirements = document.getElementById('guide-requirements');
  const state = document.getElementById('guide-state');
  const printerFilter = document.getElementById('guide-printer-filter');
  const results = document.getElementById('guide-results');
  const heading = document.getElementById('guide-heading');
  const realFilters = [...document.querySelectorAll('[data-guide-filter]')];
  const resetFilters = document.getElementById('guide-reset-filters');

  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const numberFrom = (value) => {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    const matches = String(value ?? '').match(/-?\d+(?:[.,]\d+)?/g);
    if (!matches?.length) return null;
    const numbers = matches.slice(0, 2).map((item) => Number(item.replace(',', '.')));
    return numbers.length === 1 ? numbers[0] : numbers.reduce((sum, item) => sum + item, 0) / numbers.length;
  };
  const value = (material, key) => Number((material.scores?.[state.value] || material.scores?.dry || {})[key] ?? 0);
  const realValue = (material, key) => {
    const real = material.real_properties?.[key]?.value;
    return numberFrom(real ?? material.properties?.[key]);
  };
  const realLabel = (material, key, fallback = '—') => material.real_properties?.[key]?.label || material.properties?.[key] || fallback;
  const maxScore = (rows) => Math.max(...rows.map((row) => row.rank), 1);
  const metric = (material, keys) => keys.reduce((sum, [key, weight]) => sum + value(material, key) * weight, 0);
  const materialKeys = (material) => new Set([...(material.filter_keys || []), ...(material.compatibility?.filter_keys || [])]);
  const hasKey = (material, key) => materialKeys(material).has(key);
  const statusPenalty = (material) => {
    const status = material.compatibility?.preferred_printer_result?.status;
    if (status === 'recommended') return 0;
    if (status === 'precautions') return 0.7;
    if (status === 'needs_confirmation') return 1.4;
    if (status === 'not_recommended') return 2.2;
    return 0.8;
  };
  const easyPrintScore = (m) => {
    const nozzle = Number(m.compatibility?.nozzle_max_c || 0);
    const bed = Number(m.compatibility?.bed_max_c || 0);
    const processPenalty = (nozzle > 280 ? 1.5 : nozzle > 260 ? 0.7 : 0)
      + (bed > 100 ? 0.8 : 0)
      + (m.compatibility?.requires_enclosure ? 1.4 : 0)
      + (hasKey(m, 'hardened-nozzle') ? 1.0 : 0)
      + (!m.compatibility?.ams ? 0.4 : 0)
      + statusPenalty(m);
    return metric(m, [['printability', 1.25], ['moisture_tolerance', 0.55], ['layer_adhesion', 0.18]]) - processPenalty;
  };

  const filterValue = (key) => Number(document.querySelector(`[data-guide-filter="${key}"]`)?.value || 0);
  const filterActive = () => realFilters.some((input) => Number(input.value) > 0);
  const updateFilterOutputs = () => {
    const labels = {
      'min-hdt': (value) => value > 0 ? `${value} °C+` : 'Any',
      'min-tensile': (value) => value > 0 ? `${value} MPa+` : 'Any',
      'min-modulus': (value) => value > 0 ? `${value} GPa+` : 'Any',
      'max-price': (value) => value > 0 ? `€${value}/kg max` : 'Any',
    };
    realFilters.forEach((input) => {
      const output = document.querySelector(`[data-guide-output="${input.dataset.guideFilter}"]`);
      if (output) output.textContent = labels[input.dataset.guideFilter](Number(input.value));
    });
  };
  const passesRealFilters = (material) => {
    const minHdt = filterValue('min-hdt');
    const minTensile = filterValue('min-tensile');
    const minModulus = filterValue('min-modulus');
    const maxPrice = filterValue('max-price');
    if (minHdt > 0 && (realValue(material, 'hdt_c') ?? -Infinity) < minHdt) return false;
    if (minTensile > 0 && (realValue(material, 'tensile_mpa') ?? -Infinity) < minTensile) return false;
    if (minModulus > 0 && (realValue(material, 'modulus_gpa') ?? -Infinity) < minModulus) return false;
    if (maxPrice > 0 && (realValue(material, 'price_per_kg') ?? Infinity) > maxPrice) return false;
    return true;
  };

  const scoring = {
    general: (m) => metric(m, [['printability',1.1],['strength_xy',.8],['impact_resistance',.6],['water_resistance',.4]]) - value(m,'price_range')*.12,
    outdoor: (m) => metric(m, [['uv_resistance',1.2],['water_resistance',.8],['heat_resistance',.7]]),
    flexible: (m) => metric(m, [['impact_resistance',.8],['layer_adhesion',.4]]) + (hasKey(m, 'group-elastomer') ? 14 : 0) - value(m,'rigidity_xy')*.35,
    heat: (m) => metric(m, [['heat_resistance',1.3],['creep_resistance',.45]]) + Math.min((realValue(m,'hdt_c') || 0)/45, 5),
    stiff: (m) => metric(m, [['rigidity_xy',1.3],['strength_xy',.7],['creep_resistance',.45]]),
    impact: (m) => metric(m, [['impact_resistance',1.25],['layer_adhesion',.85],['strength_xy',.2]]),
    chemical: (m) => metric(m, [['chemical_resistance',1.1],['water_resistance',.9],['moisture_tolerance',.35]]),
    cheap: (m) => metric(m, [['printability',.8],['strength_xy',.3]]) + (11-value(m,'price_range'))*1.25,
    easy: easyPrintScore,
  };

  const whyHigh = (m, needs) => {
    const notes = [];
    if (needs.has('heat')) notes.push(`heat score ${value(m,'heat_resistance')}/10, HDT ${realLabel(m, 'hdt_c')}`);
    if (needs.has('stiff')) notes.push(`XY rigidity ${value(m,'rigidity_xy')}/10, modulus ${realLabel(m, 'modulus_gpa')}`);
    if (needs.has('impact')) notes.push(`impact ${value(m,'impact_resistance')}/10 and layer bond ${value(m,'layer_adhesion')}/10`);
    if (needs.has('outdoor')) notes.push(`UV ${value(m,'uv_resistance')}/10 and water ${value(m,'water_resistance')}/10`);
    if (needs.has('chemical')) notes.push(`chemical ${value(m,'chemical_resistance')}/10 and water ${value(m,'water_resistance')}/10`);
    if (needs.has('cheap')) notes.push(`lower price score ${value(m,'price_range')}/10, tracked price ${realLabel(m, 'price_per_kg', 'not saved')}`);
    if (needs.has('easy')) notes.push(`printability ${value(m,'printability')}/10 and moisture tolerance ${value(m,'moisture_tolerance')}/10`);
    if (needs.has('flexible')) notes.push(hasKey(m, 'group-elastomer') ? 'elastomer family match' : `impact ${value(m,'impact_resistance')}/10`);
    if (!notes.length) notes.push(`printability ${value(m,'printability')}/10, tensile ${realLabel(m, 'tensile_mpa')}`);
    return notes.slice(0, 2).join(' · ');
  };
  const whyFail = (m) => {
    if (Number(m.properties?.moisture_sensitivity || 0) >= 8) return 'Moisture can change the result; dry and store carefully.';
    if (m.compatibility?.preferred_printer_result?.status === 'needs_confirmation') return 'Nozzle or tool capability still needs confirmation on the selected printer.';
    if (m.compatibility?.requires_enclosure) return 'Enclosure or chamber control may be needed for reliable printing.';
    if (value(m, 'impact_resistance') <= 3) return 'Likely stiff but not forgiving under impact.';
    if (value(m, 'heat_resistance') <= 3) return 'Heat resistance is limited for warm/load-bearing parts.';
    if (!m.compatibility?.ams) return 'AMS or multi-spool feeding may be risky.';
    return 'No obvious blocker from the selected filters, but exact product data still matters.';
  };
  const verify = (m) => {
    const items = ['exact spool TDS'];
    if (!m.compatibility?.ams) items.push('filament path');
    if (Number(m.properties?.moisture_sensitivity || 0) >= 6) items.push('drying state');
    if (hasKey(m, 'hardened-nozzle')) items.push('nozzle material/diameter');
    items.push('printed load direction');
    return items.slice(0, 4).join(' · ');
  };

  const render = () => {
    updateFilterOutputs();
    const selectedFilter = printerFilter?.value || 'all';
    const candidates = materials.filter((material) => {
      if (selectedFilter !== 'all' && !(material.compatibility?.filter_keys || []).includes(selectedFilter)) return false;
      return passesRealFilters(material);
    });
    if (!candidates.length) {
      heading.textContent = 'No material matches those requirements.';
      results.innerHTML = '<div class="empty-state">Relax one advanced real-value filter, choose another printer/path, or add an exact spool price/TDS value to compare against.</div>';
      return;
    }
    const ranked = candidates
      .map((material) => ({...material, rank:[...selected].reduce((sum, need) => sum + scoring[need](material),0)}))
      .sort((a,b)=>b.rank-a.rank)
      .slice(0,6);
    const top = maxScore(ranked);
    const filterLabel = printerFilter?.selectedOptions?.[0]?.textContent || 'all printers';
    heading.textContent = `${ranked.length} materials ranked for ${[...selected].join(' + ')} on ${filterLabel}${filterActive() ? ' with real-value filters' : ''}.`;
    results.innerHTML = ranked.map((m, index) => {
      const pct = Math.max(8, m.rank / top * 100);
      return `<a class="guide-result guide-result--explained" style="--material-color:${esc(m.family_color)}" href="/materials/${esc(m.slug)}">
        <div class="guide-rank">${index+1}</div>
        <div class="guide-result-main">
          <div class="material-card-top"><span class="family-pill">${esc(m.family)}</span><span class="subfamily-pill">${esc(m.subfamily)}</span></div>
          <h3>${esc(m.name)}</h3>
          <p>${esc(m.best_for)}</p>
          <div class="guide-bar"><i style="width:${pct}%"></i></div>
          <div class="guide-reason-grid">
            <span><b>Why this ranked high</b>${esc(whyHigh(m, selected))}</span>
            <span><b>Why this might fail</b>${esc(whyFail(m))}</span>
            <span><b>Verify before buying</b>${esc(verify(m))}</span>
          </div>
        </div>
        <div class="guide-caution">
          <b>${esc(realLabel(m, 'hdt_c'))} HDT</b>
          <span>${esc(realLabel(m, 'tensile_mpa'))} tensile</span>
          <span>${esc(realLabel(m, 'price_per_kg', 'No tracked price'))}</span>
        </div>
        <strong class="guide-arrow">→</strong>
      </a>`;
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
  printerFilter?.addEventListener('change', render);
  realFilters.forEach((input) => input.addEventListener('input', render));
  resetFilters?.addEventListener('click', () => {
    realFilters.forEach((input) => { input.value = 0; });
    render();
  });
  requirements.querySelectorAll('button').forEach((button) => button.classList.toggle('is-selected', selected.has(button.dataset.need)));
  render();
})();
