(() => {
  const dataEl = document.getElementById('compare-material-data');
  if (!dataEl) return;

  const materials = JSON.parse(dataEl.textContent);
  const familyPicker = document.getElementById('compare-family-picker');
  const picker = document.getElementById('compare-picker');
  const materialSearch = document.getElementById('compare-material-search');
  const selectedCount = document.getElementById('compare-selected-count');
  const clearButton = document.getElementById('compare-clear');
  const stateSelect = document.getElementById('compare-state');
  const propertySelect = document.getElementById('compare-property');
  const scatterXSelect = document.getElementById('scatter-x-property');
  const scatterYSelect = document.getElementById('scatter-y-property');
  const radarTarget = document.getElementById('radar-chart');
  const barTarget = document.getElementById('bar-chart');
  const scatterTarget = document.getElementById('scatter-chart');
  const tableBody = document.querySelector('#compare-table tbody');
  const barTitle = document.getElementById('bar-chart-title');
  const scatterTitle = document.getElementById('scatter-chart-title');
  const scatterNote = document.getElementById('scatter-chart-note');

  const radarAxis = [
    ['rigidity_xy', 'XY rigidity'],
    ['strength_xy', 'XY strength'],
    ['layer_adhesion', 'Layer bond'],
    ['impact_resistance', 'Impact'],
    ['heat_resistance', 'Heat'],
    ['chemical_resistance', 'Chemical'],
    ['water_resistance', 'Water'],
    ['printability', 'Printability'],
  ];

  const scoreMetrics = {
    rigidity_xy: { label: 'XY rigidity', unit: '/10', better: 'higher' },
    strength_xy: { label: 'XY strength', unit: '/10', better: 'higher' },
    rigidity_z: { label: 'Z rigidity', unit: '/10', better: 'higher' },
    layer_adhesion: { label: 'Layer adhesion', unit: '/10', better: 'higher' },
    impact_resistance: { label: 'Impact resistance', unit: '/10', better: 'higher' },
    heat_resistance: { label: 'Heat resistance', unit: '/10', better: 'higher' },
    chemical_resistance: { label: 'Chemical resistance', unit: '/10', better: 'higher' },
    water_resistance: { label: 'Water resistance', unit: '/10', better: 'higher' },
    moisture_tolerance: { label: 'Moisture tolerance', unit: '/10', better: 'higher' },
    printability: { label: 'Ease of printing', unit: '/10', better: 'higher' },
    creep_resistance: { label: 'Creep resistance', unit: '/10', better: 'higher' },
    uv_resistance: { label: 'UV resistance', unit: '/10', better: 'higher' },
  };

  const realMetrics = {
    price_per_kg: { label: 'Current price', unit: '€/kg', better: 'lower' },
    tensile_mpa: { label: 'Tensile strength', unit: 'MPa', better: 'higher' },
    modulus_gpa: { label: 'Tensile modulus', unit: 'GPa', better: 'higher' },
    hdt_c: { label: 'HDT', unit: '°C', better: 'higher' },
    continuous_service_c: { label: 'Continuous service', unit: '°C', better: 'higher' },
    density_g_cm3: { label: 'Density', unit: 'g/cm³', better: 'neutral' },
    moisture_sensitivity: { label: 'Moisture sensitivity', unit: '/10', better: 'lower' },
  };

  const esc = (value) => String(value ?? '').replace(/[&<>"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
  const color = (material) => material.family_color || '#8b5cf6';
  const selectionPalette = ['#2dd4bf', '#f472b6', '#f59e0b', '#60a5fa', '#a3e635', '#c084fc'];
  const assignedColors = new Map();
  const ensureAssignedColor = (slug) => {
    if (!assignedColors.has(slug)) {
      const usedColors = new Set([...selectedSlugs].map((selectedSlug) => assignedColors.get(selectedSlug)).filter(Boolean));
      const availableColor = selectionPalette.find((candidate) => !usedColors.has(candidate))
        || selectionPalette[assignedColors.size % selectionPalette.length];
      assignedColors.set(slug, availableColor);
    }
    return assignedColors.get(slug);
  };
  const compareColor = (material) => selectedSlugs.has(material.slug)
    ? ensureAssignedColor(material.slug)
    : color(material);
  const normalizeSearch = (value) => String(value ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
  const initialMaterials = materials.filter((material) => !material.is_catalog).slice(0, 4);
  const selectedSlugs = new Set((initialMaterials.length ? initialMaterials : materials.slice(0, 4)).map((material) => material.slug));
  selectedSlugs.forEach(ensureAssignedColor);
  let activeFamily = initialMaterials.length ? 'saved' : 'group-pla';
  const familyGroups = [
    { key: 'saved', label: 'Saved materials' },
    { key: 'group-pla', label: 'PLA' },
    { key: 'group-polyester', label: 'PET / copolyester' },
    { key: 'group-styrenic', label: 'ABS / ASA' },
    { key: 'group-elastomer', label: 'Flexible' },
    { key: 'group-polyamide', label: 'Nylon / PA' },
    { key: 'group-pc', label: 'PC / blends' },
    { key: 'group-high-temp', label: 'High-temp' },
    { key: 'group-support', label: 'Support' },
    { key: 'group-filled', label: 'Filled / abrasive' },
    { key: 'group-esd', label: 'ESD / conductive' },
    { key: 'group-polyolefin', label: 'PP / polyolefin' },
    { key: 'catalog-backlog', label: 'All catalog' },
  ];
  const materialKeys = (material) => new Set([
    ...(material.filter_keys || []),
    ...(material.compatibility?.filter_keys || []),
  ]);
  const groupMatches = (material, key) => {
    if (key === 'saved') return !material.is_catalog;
    return materialKeys(material).has(key);
  };
  const groupCounts = () => familyGroups
    .map((group) => ({ ...group, count: materials.filter((material) => groupMatches(material, group.key)).length }))
    .filter((group) => group.count > 0);
  const selectedMaterials = () => materials.filter((material) => selectedSlugs.has(material.slug));
  const metricParts = (metricId) => {
    const [kind, key] = String(metricId || '').split(':');
    return { kind: kind || 'score', key };
  };
  const metricConfig = (metricId) => {
    const { kind, key } = metricParts(metricId);
    const config = kind === 'real' ? realMetrics[key] : scoreMetrics[key];
    return { kind, key, ...(config || { label: key || 'Unknown', unit: '', better: 'neutral' }) };
  };
  const score = (material, key) => {
    const state = stateSelect.value;
    return Number((material.scores?.[state] || material.scores?.dry || {})[key] ?? 0);
  };
  const realEntry = (material, key) => material.real_properties?.[key] || {};
  const metricValue = (material, metricId) => {
    const metric = metricConfig(metricId);
    if (metric.kind === 'score') return score(material, metric.key);
    const value = Number(realEntry(material, metric.key).value);
    return Number.isFinite(value) ? value : null;
  };
  const metricText = (material, metricId) => {
    const metric = metricConfig(metricId);
    if (metric.kind === 'score') return scoreText(metricValue(material, metricId));
    const entry = realEntry(material, metric.key);
    return entry.label || '—';
  };
  const scoreText = (n) => `${Math.round(Number(n || 0) * 10) / 10}/10`;
  const compactNumber = (value) => {
    const number = Number(value);
    if (!Number.isFinite(number)) return '—';
    if (Math.abs(number) >= 100) return Math.round(number).toString();
    return (Math.round(number * 100) / 100).toString();
  };
  const formatValue = (value, metric) => {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
    const rounded = Math.round(Number(value) * 100) / 100;
    if (metric.kind === 'score') return scoreText(rounded);
    if (metric.key === 'price_per_kg') return `€${rounded.toFixed(2)}/kg`;
    return compactNumber(rounded) + (metric.unit ? ` ${metric.unit}` : '');
  };
  const valueDomain = (selected, metricId) => {
    const metric = metricConfig(metricId);
    if (metric.kind === 'score') {
      return { min: 0, max: 10, ticks: [0, 2, 4, 6, 8, 10] };
    }

    const values = selected
      .map((material) => metricValue(material, metricId))
      .filter((value) => value !== null);
    if (!values.length) return { min: 0, max: 1, ticks: [0, 0.5, 1] };

    const max = Math.max(...values);
    const paddedMax = max <= 0 ? 1 : max * 1.12;
    const step = paddedMax / 5;
    return {
      min: 0,
      max: paddedMax,
      ticks: [0, 1, 2, 3, 4, 5].map((n) => n * step),
    };
  };
  const scale = (value, domain, pixels) => {
    if (value === null || domain.max === domain.min) return 0;
    return Math.max(0, Math.min(pixels, pixels * (value - domain.min) / (domain.max - domain.min)));
  };
  const betterHint = (metric) => {
    if (metric.better === 'higher') return 'Higher is stronger/better for this comparison.';
    if (metric.better === 'lower') return metric.key === 'price_per_kg' ? 'Lower is cheaper.' : 'Lower is better for this metric.';
    return 'Use this as a real reference value, not a simple better/worse score.';
  };

  const materialSearchText = (material) => normalizeSearch([
    material.name,
    material.full_name,
    material.family,
    material.subfamily,
    material.best_for,
    material.avoid_for,
    material.search,
    [...materialKeys(material)].join(' '),
  ].join(' '));

  const renderFamilyPicker = () => {
    const groups = groupCounts();
    if (!groups.some((group) => group.key === activeFamily)) {
      activeFamily = groups[0]?.key || 'saved';
    }

    familyPicker.innerHTML = groups.map((group) => (
      `<button class="chip compare-family-chip ${group.key === activeFamily ? 'is-selected' : ''}" type="button" data-compare-family="${esc(group.key)}">${esc(group.label)} <span>${group.count}</span></button>`
    )).join('');
  };

  const renderPicker = () => {
    const terms = normalizeSearch(materialSearch?.value || '').split(/\s+/).filter(Boolean);
    const options = materials
      .filter((material) => groupMatches(material, activeFamily))
      .filter((material) => !terms.length || terms.every((term) => materialSearchText(material).includes(term)))
      .sort((a, b) => Number(a.is_catalog) - Number(b.is_catalog) || a.name.localeCompare(b.name));

    if (selectedCount) {
      selectedCount.textContent = `${selectedSlugs.size}/6 selected`;
    }

    if (!options.length) {
      picker.innerHTML = '<div class="empty-state">No materials in this group match that search.</div>';
      return;
    }

    picker.innerHTML = options.map((material) => {
      const checked = selectedSlugs.has(material.slug);
      const disabled = selectedSlugs.size >= 6 && !checked;
      const label = material.is_catalog ? 'Catalog' : 'Saved';
      const optionColor = checked ? compareColor(material) : color(material);
      return `<label class="compare-option ${disabled ? 'is-disabled' : ''}" style="--material-color: ${esc(optionColor)}">
        <input type="checkbox" value="${esc(material.slug)}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
        <span class="compare-swatch"></span>
        <b>${esc(material.name)}</b>
        <small>${esc(material.subfamily)} · ${label}</small>
      </label>`;
    }).join('');
  };

  const point = (cx, cy, radius, index, value, count) => {
    const angle = (Math.PI * 2 * index / count) - Math.PI / 2;
    const r = radius * value / 10;
    return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r];
  };
  const linePoint = (cx, cy, radius, index, count) => point(cx, cy, radius, index, 10, count);

  const renderRadar = (selected) => {
    if (!selected.length) {
      radarTarget.innerHTML = '<div class="empty-state">Pick one or more materials above.</div>';
      return;
    }

    const size = 420;
    const cx = 210;
    const cy = 207;
    const radius = 143;
    const count = radarAxis.length;
    let grid = '';
    [2, 4, 6, 8, 10].forEach((level) => {
      const points = radarAxis.map((_, i) => point(cx, cy, radius, i, level, count).join(',')).join(' ');
      grid += `<polygon points="${points}" fill="none" stroke="rgba(164,184,255,.18)" stroke-width="1"/>`;
    });

    let axes = '';
    radarAxis.forEach(([, label], i) => {
      const [x, y] = linePoint(cx, cy, radius, i, count);
      const [tx, ty] = linePoint(cx, cy, radius + 27, i, count);
      axes += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="rgba(164,184,255,.20)" stroke-width="1"/>`;
      axes += `<text x="${tx}" y="${ty}" fill="#9ca9ca" font-size="10" text-anchor="middle" dominant-baseline="middle">${label}</text>`;
    });

    const polys = selected.map((material) => {
      const points = radarAxis.map(([key], i) => point(cx, cy, radius, i, score(material, key), count).join(',')).join(' ');
      return `<polygon points="${points}" fill="${compareColor(material)}" fill-opacity="0.12" stroke="${compareColor(material)}" stroke-width="2"/>`;
    }).join('');
    const legend = selected.map((material) => `<span><i style="background:${compareColor(material)}"></i>${esc(material.name)}</span>`).join('');
    radarTarget.innerHTML = `<svg viewBox="0 0 ${size} ${size}" role="img" aria-label="Material radar chart">${grid}${axes}${polys}</svg><div class="chart-key">${legend}</div>`;
  };

  const renderBars = (selected) => {
    if (!selected.length) {
      barTarget.innerHTML = '<div class="empty-state">Pick one or more materials above.</div>';
      return;
    }

    const metricId = propertySelect.value;
    const metric = metricConfig(metricId);
    const domain = valueDomain(selected, metricId);
    barTitle.textContent = `${metric.label} — ${metric.kind === 'score' ? stateSelect.options[stateSelect.selectedIndex].text : 'real values'}`;

    const w = 560;
    const h = Math.max(230, selected.length * 58 + 48);
    const left = 136;
    const right = 48;
    const top = 22;
    const usable = w - left - right;
    let guide = '';
    domain.ticks.forEach((tick) => {
      const x = left + scale(tick, domain, usable);
      guide += `<line x1="${x}" y1="${top}" x2="${x}" y2="${h - 24}" stroke="rgba(164,184,255,.12)"/><text x="${x}" y="${h - 6}" fill="#7080a8" font-size="9" text-anchor="middle">${esc(formatValue(tick, metric))}</text>`;
    });

    const bars = selected.map((material, index) => {
      const y = top + index * 56;
      const value = metricValue(material, metricId);
      const width = scale(value, domain, usable);
      const label = metricText(material, metricId);
      const valueTextX = value === null ? left + 8 : Math.min(left + width + 8, w - 96);
      const valueText = value === null ? 'No value' : label;
      return `<text x="${left - 10}" y="${y + 17}" fill="#dbe4ff" font-size="11" text-anchor="end">${esc(material.name)}</text><rect x="${left}" y="${y}" width="${usable}" height="26" rx="7" fill="rgba(164,184,255,.10)"/><rect x="${left}" y="${y}" width="${width}" height="26" rx="7" fill="${compareColor(material)}" fill-opacity=".88"/><text x="${valueTextX}" y="${y + 17}" fill="#eef2ff" font-size="10">${esc(valueText)}</text>`;
    }).join('');
    barTarget.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Material bar chart">${guide}${bars}</svg><div class="chart-key"><span>${esc(betterHint(metric))}</span></div>`;
  };

  const renderScatter = (selected) => {
    if (!selected.length) {
      scatterTarget.innerHTML = '<div class="empty-state">Pick one or more materials above.</div>';
      return;
    }

    const xId = scatterXSelect.value;
    const yId = scatterYSelect.value;
    const xMetric = metricConfig(xId);
    const yMetric = metricConfig(yId);
    const xDomain = valueDomain(selected, xId);
    const yDomain = valueDomain(selected, yId);
    const plotted = selected
      .map((material) => ({ material, x: metricValue(material, xId), y: metricValue(material, yId) }))
      .filter((item) => item.x !== null && item.y !== null);

    scatterTitle.textContent = `${yMetric.label} vs ${xMetric.label}`;
    scatterNote.textContent = `${betterHint(xMetric)} ${betterHint(yMetric)}`;

    const w = 900;
    const h = 350;
    const pad = { l: 82, r: 42, t: 22, b: 60 };
    const ux = w - pad.l - pad.r;
    const uy = h - pad.t - pad.b;
    let grid = '';
    xDomain.ticks.forEach((tick) => {
      const x = pad.l + scale(tick, xDomain, ux);
      grid += `<line x1="${x}" y1="${pad.t}" x2="${x}" y2="${pad.t + uy}" stroke="rgba(164,184,255,.10)"/><text x="${x}" y="${h - 34}" fill="#7080a8" font-size="9" text-anchor="middle">${esc(formatValue(tick, xMetric))}</text>`;
    });
    yDomain.ticks.forEach((tick) => {
      const y = pad.t + uy - scale(tick, yDomain, uy);
      grid += `<line x1="${pad.l}" y1="${y}" x2="${pad.l + ux}" y2="${y}" stroke="rgba(164,184,255,.10)"/><text x="${pad.l - 10}" y="${y + 3}" fill="#7080a8" font-size="9" text-anchor="end">${esc(formatValue(tick, yMetric))}</text>`;
    });

    const dots = plotted.map((item, index) => {
      const x = pad.l + scale(item.x, xDomain, ux);
      const y = pad.t + uy - scale(item.y, yDomain, uy);
      const dy = index % 2 ? -11 : 18;
      return `<circle cx="${x}" cy="${y}" r="7" fill="${compareColor(item.material)}" stroke="#0b1020" stroke-width="3"/><text x="${x + 10}" y="${y + dy}" fill="#e8edff" font-size="10">${esc(item.material.name)}</text>`;
    }).join('');
    const missing = selected.length - plotted.length;
    const missingNote = missing ? `<div class="chart-key"><span>${missing} selected material${missing === 1 ? '' : 's'} had no real value for one axis.</span></div>` : '';
    scatterTarget.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Material trade-off map"><text x="${pad.l + ux / 2}" y="${h - 8}" fill="#9ca9ca" font-size="11" text-anchor="middle">${esc(xMetric.label)}${xMetric.unit ? ` (${esc(xMetric.unit)})` : ''} →</text><text x="18" y="${pad.t + uy / 2}" fill="#9ca9ca" font-size="11" text-anchor="middle" transform="rotate(-90 18 ${pad.t + uy / 2})">${esc(yMetric.label)}${yMetric.unit ? ` (${esc(yMetric.unit)})` : ''} →</text>${grid}${dots}</svg>${missingNote}`;
  };

  const renderTable = (selected) => {
    const state = stateSelect.value === 'dry' ? 'Dry' : 'Conditioned / wet';
    tableBody.innerHTML = selected.map((material) => {
      const real = material.real_properties || {};
      return `<tr><td><strong>${esc(material.name)}</strong><br><small>${esc(material.subfamily)}</small></td><td>${state}</td><td>${esc(real.density_g_cm3?.label || '—')}</td><td>${esc(real.hdt_c?.label || '—')}</td><td>${esc(real.continuous_service_c?.label || '—')}</td><td>${esc(real.tensile_mpa?.label || '—')}</td><td>${esc(real.modulus_gpa?.label || '—')}</td><td>${scoreText(score(material, 'strength_xy'))}</td><td>${scoreText(score(material, 'impact_resistance'))}</td><td>${esc(real.price_per_kg?.label || '—')}</td></tr>`;
    }).join('') || '<tr><td colspan="10" class="muted-cell">Select materials to populate the table.</td></tr>';
  };

  const renderCharts = () => {
    const selected = selectedMaterials();
    renderRadar(selected);
    renderBars(selected);
    renderScatter(selected);
    renderTable(selected);
  };

  const renderAll = () => {
    renderFamilyPicker();
    renderPicker();
    renderCharts();
  };

  familyPicker?.addEventListener('click', (event) => {
    const button = event.target.closest('[data-compare-family]');
    if (!button) return;
    activeFamily = button.dataset.compareFamily;
    if (materialSearch) materialSearch.value = '';
    renderAll();
  });

  materialSearch?.addEventListener('input', renderPicker);

  picker.addEventListener('change', (event) => {
    const input = event.target.closest('input[type="checkbox"]');
    if (!input) return;

    if (input.checked) {
      if (selectedSlugs.size >= 6 && !selectedSlugs.has(input.value)) {
        input.checked = false;
        window.alert('Keep six materials or fewer for a readable comparison.');
        return;
      }
      selectedSlugs.add(input.value);
      ensureAssignedColor(input.value);
    } else {
      selectedSlugs.delete(input.value);
    }

    renderAll();
  });

  clearButton?.addEventListener('click', () => {
    selectedSlugs.clear();
    assignedColors.clear();
    renderAll();
  });

  stateSelect.addEventListener('change', renderCharts);
  propertySelect.addEventListener('change', renderCharts);
  scatterXSelect.addEventListener('change', renderCharts);
  scatterYSelect.addEventListener('change', renderCharts);
  renderAll();
})();
