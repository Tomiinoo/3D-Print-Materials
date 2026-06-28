(() => {
  const dataEl = document.getElementById('compare-material-data');
  if (!dataEl) return;
  const materials = JSON.parse(dataEl.textContent);
  const picker = document.getElementById('compare-picker');
  const stateSelect = document.getElementById('compare-state');
  const propertySelect = document.getElementById('compare-property');
  const radarTarget = document.getElementById('radar-chart');
  const barTarget = document.getElementById('bar-chart');
  const scatterTarget = document.getElementById('scatter-chart');
  const tableBody = document.querySelector('#compare-table tbody');
  const barTitle = document.getElementById('bar-chart-title');
  const axis = [
    ['rigidity_xy', 'XY rigidity'],
    ['strength_xy', 'XY strength'],
    ['layer_adhesion', 'Layer bond'],
    ['impact_resistance', 'Impact'],
    ['heat_resistance', 'Heat'],
    ['chemical_resistance', 'Chemical'],
    ['water_resistance', 'Water'],
    ['printability', 'Printability'],
  ];
  const labels = {
    rigidity_xy: 'XY rigidity', strength_xy: 'XY strength', rigidity_z: 'Z rigidity', layer_adhesion: 'Layer adhesion',
    impact_resistance: 'Impact resistance', heat_resistance: 'Heat resistance', chemical_resistance: 'Chemical resistance',
    water_resistance: 'Water resistance', moisture_tolerance: 'Moisture tolerance', printability: 'Ease of printing',
    creep_resistance: 'Creep resistance', uv_resistance: 'UV resistance', price_range: 'Price range',
  };
  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const color = (material) => material.family_color || '#8b5cf6';
  const selectedMaterials = () => {
    const selectedSlugs = [...picker.querySelectorAll('input:checked')].map((input) => input.value);
    return materials.filter((material) => selectedSlugs.includes(material.slug));
  };
  const score = (material, key) => {
    const state = stateSelect.value;
    return Number((material.scores?.[state] || material.scores?.dry || {})[key] ?? 0);
  };
  const point = (cx, cy, radius, index, value, count) => {
    const angle = (Math.PI * 2 * index / count) - Math.PI / 2;
    const r = radius * value / 10;
    return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r];
  };
  const linePoint = (cx, cy, radius, index, count) => point(cx, cy, radius, index, 10, count);
  const scoreText = (n) => `${Math.round(n * 10) / 10}/10`;

  const renderRadar = (selected) => {
    if (!selected.length) { radarTarget.innerHTML = '<div class="empty-state">Pick one or more materials above.</div>'; return; }
    const size = 420; const cx = 210; const cy = 207; const radius = 143; const count = axis.length;
    let grid = '';
    [2,4,6,8,10].forEach((level) => {
      const points = axis.map((_, i) => point(cx, cy, radius, i, level, count).join(',')).join(' ');
      grid += `<polygon points="${points}" fill="none" stroke="rgba(164,184,255,.18)" stroke-width="1"/>`;
    });
    let axes = '';
    axis.forEach(([, label], i) => {
      const [x,y] = linePoint(cx, cy, radius, i, count);
      const [tx,ty] = linePoint(cx, cy, radius + 27, i, count);
      axes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="rgba(164,184,255,.20)" stroke-width="1"/>`;
      axes += `<text x="${tx}" y="${ty}" fill="#9ca9ca" font-size="10" text-anchor="middle" dominant-baseline="middle">${label}</text>`;
    });
    const polys = selected.map((material) => {
      const points = axis.map(([key], i) => point(cx, cy, radius, i, score(material, key), count).join(',')).join(' ');
      return `<polygon points="${points}" fill="${color(material)}" fill-opacity="0.12" stroke="${color(material)}" stroke-width="2"/>`;
    }).join('');
    const legend = selected.map((material) => `<span><i style="background:${color(material)}"></i>${esc(material.name)}</span>`).join('');
    radarTarget.innerHTML = `<svg viewBox="0 0 ${size} ${size}" role="img" aria-label="Material radar chart">${grid}${axes}${polys}</svg><div class="chart-key">${legend}</div>`;
  };

  const renderBars = (selected) => {
    if (!selected.length) { barTarget.innerHTML = '<div class="empty-state">Pick one or more materials above.</div>'; return; }
    const key = propertySelect.value;
    const label = labels[key] || key;
    barTitle.textContent = `${label} — ${stateSelect.options[stateSelect.selectedIndex].text}`;
    const w = 540; const h = Math.max(220, selected.length * 54 + 40); const left = 128; const right = 36; const top = 20; const usable = w-left-right;
    let guide = '';
    for (let level = 0; level <= 10; level += 2) {
      const x = left + usable * level / 10;
      guide += `<line x1="${x}" y1="${top}" x2="${x}" y2="${h-20}" stroke="rgba(164,184,255,.12)"/><text x="${x}" y="${h-5}" fill="#7080a8" font-size="9" text-anchor="middle">${level}</text>`;
    }
    const bars = selected.map((material, index) => {
      const y = top + index * 52;
      const val = score(material, key);
      const width = usable * val / 10;
      return `<text x="${left-10}" y="${y+16}" fill="#dbe4ff" font-size="11" text-anchor="end">${esc(material.name)}</text><rect x="${left}" y="${y}" width="${usable}" height="24" rx="6" fill="rgba(164,184,255,.10)"/><rect x="${left}" y="${y}" width="${width}" height="24" rx="6" fill="${color(material)}" fill-opacity=".88"/><text x="${Math.min(left+width+7, w-6)}" y="${y+16}" fill="#eef2ff" font-size="10">${scoreText(val)}</text>`;
    }).join('');
    barTarget.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Material bar chart">${guide}${bars}</svg>`;
  };

  const renderScatter = (selected) => {
    if (!selected.length) { scatterTarget.innerHTML = '<div class="empty-state">Pick one or more materials above.</div>'; return; }
    const w = 900; const h = 350; const pad = {l:70,r:35,t:22,b:55}; const ux = w-pad.l-pad.r; const uy = h-pad.t-pad.b;
    let grid = '';
    for (let n=0; n<=10; n+=2) {
      const x=pad.l+ux*n/10; const y=pad.t+uy-(uy*n/10);
      grid += `<line x1="${x}" y1="${pad.t}" x2="${x}" y2="${pad.t+uy}" stroke="rgba(164,184,255,.10)"/><text x="${x}" y="${h-30}" fill="#7080a8" font-size="10" text-anchor="middle">${n}</text>`;
      grid += `<line x1="${pad.l}" y1="${y}" x2="${pad.l+ux}" y2="${y}" stroke="rgba(164,184,255,.10)"/><text x="${pad.l-10}" y="${y+3}" fill="#7080a8" font-size="10" text-anchor="end">${n}</text>`;
    }
    const dots = selected.map((material, index) => {
      const x = pad.l + ux * score(material,'impact_resistance') / 10;
      const y = pad.t + uy - uy * score(material,'heat_resistance') / 10;
      const dy = index % 2 ? -11 : 18;
      return `<circle cx="${x}" cy="${y}" r="7" fill="${color(material)}" stroke="#0b1020" stroke-width="3"/><text x="${x+10}" y="${y+dy}" fill="#e8edff" font-size="10">${esc(material.name)}</text>`;
    }).join('');
    scatterTarget.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Heat and impact comparison"><text x="${pad.l+ux/2}" y="${h-7}" fill="#9ca9ca" font-size="11" text-anchor="middle">Impact resistance →</text><text x="17" y="${pad.t+uy/2}" fill="#9ca9ca" font-size="11" text-anchor="middle" transform="rotate(-90 17 ${pad.t+uy/2})">Heat resistance →</text>${grid}${dots}</svg>`;
  };

  const renderTable = (selected) => {
    const state = stateSelect.value === 'dry' ? 'Dry' : 'Conditioned / wet';
    tableBody.innerHTML = selected.map((material) => {
      const properties = material.properties || {};
      return `<tr><td><strong>${esc(material.name)}</strong><br><small>${esc(material.subfamily)}</small></td><td>${state}</td><td>${Number(properties.density_g_cm3 || 0).toFixed(2)} g/cm³</td><td>${properties.hdt_c || '—'} °C</td><td>${properties.continuous_service_c || '—'} °C</td><td>${properties.moisture_sensitivity || 0}/10</td><td>${scoreText(score(material,'strength_xy'))}</td><td>${scoreText(score(material,'layer_adhesion'))}</td><td>${scoreText(score(material,'impact_resistance'))}</td><td>${scoreText(score(material,'price_range'))}</td></tr>`;
    }).join('') || '<tr><td colspan="10" class="muted-cell">Select materials to populate the table.</td></tr>';
  };

  const render = () => {
    const selected = selectedMaterials();
    renderRadar(selected); renderBars(selected); renderScatter(selected); renderTable(selected);
  };

  picker.addEventListener('change', (event) => {
    const checked = picker.querySelectorAll('input:checked');
    if (checked.length > 6 && event.target.checked) {
      event.target.checked = false;
      window.alert('Keep six materials or fewer for a readable comparison.');
    }
    render();
  });
  stateSelect.addEventListener('change', render);
  propertySelect.addEventListener('change', render);
  render();
})();
