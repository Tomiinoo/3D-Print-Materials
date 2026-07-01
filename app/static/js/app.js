(() => {
  const sidebar = document.getElementById('sidebar');
  document.querySelector('[data-sidebar-toggle]')?.addEventListener('click', () => sidebar?.classList.toggle('is-open'));

  const clearOptOutDateDefaults = (root = document) => {
    root.querySelectorAll('input[type="date"][data-no-default-date]').forEach((input) => {
      input.value = '';
    });
  };

  document.querySelectorAll('[data-toggle]').forEach((trigger) => {
    trigger.addEventListener('click', () => {
      const target = document.getElementById(trigger.dataset.toggle);
      if (!target) return;

      const isOpening = target.hidden;

      if (isOpening && trigger.dataset.resetForm) {
        const container = document.getElementById(trigger.dataset.resetForm);
        const form = container?.matches('form') ? container : container?.querySelector('form');

        if (form) {
          form.reset();
          clearOptOutDateDefaults(form);
        }
      }

      target.hidden = !target.hidden;
      if (isOpening && trigger.dataset.scrollTarget) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  document.querySelectorAll('input[type="date"]:not([data-no-default-date])').forEach((input) => {
    if (!input.value) input.value = new Date().toISOString().slice(0, 10);
  });

  clearOptOutDateDefaults();
  window.addEventListener('pageshow', () => clearOptOutDateDefaults());

  const wireNozzleFilters = () => {
    document.querySelectorAll('[data-printer-select]').forEach((printerSelect) => {
      const form = printerSelect.closest('form') || document;
      const nozzleSelect = form.querySelector('[data-nozzle-select]');
      if (!nozzleSelect) return;

      const updateNozzles = () => {
        const printerId = printerSelect.value;
        [...nozzleSelect.options].forEach((option) => {
          if (!option.value) {
            option.hidden = false;
            return;
          }
          option.hidden = Boolean(printerId) && option.dataset.printerId !== printerId;
        });

        const selected = nozzleSelect.selectedOptions[0];
        if (selected?.hidden) {
          nozzleSelect.value = '';
        }
      };

      printerSelect.addEventListener('change', updateNozzles);
      updateNozzles();
    });
  };

  wireNozzleFilters();

  const wireToolCards = () => {
    const list = document.querySelector('[data-tool-list]');
    const addButton = document.querySelector('[data-add-tool]');
    if (!list || !addButton) return;

    const renumber = () => {
      const cards = [...list.querySelectorAll('[data-tool-card]')];
      cards.forEach((card, index) => {
        const title = card.querySelector('.tool-card__head strong');
        if (title) title.textContent = `Tool ${index + 1}`;
        const remove = card.querySelector('[data-remove-tool]');
        if (remove) remove.disabled = cards.length === 1;
      });
    };

    addButton.addEventListener('click', () => {
      const source = list.querySelector('[data-tool-card]');
      if (!source) return;
      const clone = source.cloneNode(true);
      clone.querySelectorAll('input, textarea').forEach((field) => {
        if (field.name === 'tool_ids') field.value = '';
        else if (field.name === 'tool_names') field.value = `Tool ${list.querySelectorAll('[data-tool-card]').length + 1}`;
        else if (field.name === 'tool_max_hotend_c') field.value = source.querySelector('[name="tool_max_hotend_c"]')?.value || '';
        else field.value = '';
      });
      clone.querySelectorAll('select').forEach((select) => { select.value = 'active'; });
      list.appendChild(clone);
      renumber();
    });

    list.addEventListener('click', (event) => {
      const button = event.target.closest('[data-remove-tool]');
      if (!button || button.disabled) return;
      button.closest('[data-tool-card]')?.remove();
      renumber();
    });

    renumber();
  };

  wireToolCards();

  const catalogSearch = document.querySelector('[data-nozzle-catalog-search]');
  const catalogSelect = document.querySelector('[data-nozzle-catalog-select]');
  catalogSearch?.addEventListener('input', () => {
    const terms = normalizeSearch(catalogSearch.value).split(/\s+/).filter(Boolean);
    [...catalogSelect?.options || []].forEach((option) => {
      if (!option.value) {
        option.hidden = false;
        return;
      }
      const haystack = normalizeSearch(`${option.textContent || ''} ${option.dataset.search || ''}`);
      option.hidden = terms.length > 0 && !terms.every((term) => haystack.includes(term));
    });
    if (catalogSelect?.selectedOptions[0]?.hidden) catalogSelect.value = '';
  });

  const search = document.getElementById('material-search');
  const cards = [...document.querySelectorAll('#material-grid .material-card, #catalog-grid .material-card')];
  const empty = document.getElementById('material-empty');
  const compatFilter = document.getElementById('material-compat-filter');
  const filterReset = document.getElementById('material-filter-reset');
  const activeSummary = document.getElementById('material-active-filter');
  let selectedFilter = 'all';
  const normalizeSearch = (value) => String(value ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
  const updateMaterials = () => {
    const terms = normalizeSearch(search?.value || '').split(/\s+/).filter(Boolean);
    const compatValue = compatFilter?.value || 'all';
    let visible = 0;
    cards.forEach((card) => {
      const filters = (card.dataset.filters || '').split(/\s+/).filter(Boolean);
      const printerFilters = (card.dataset.printerFilters || '').split(/\s+/).filter(Boolean);
      const matchFilter = selectedFilter === 'all'
        || (selectedFilter.startsWith('family:') && card.dataset.family === selectedFilter.slice(7))
        || filters.includes(selectedFilter);
      const matchPrinter = compatValue === 'all'
        || (compatValue === 'saved-printers' && printerFilters.length > 0)
        || printerFilters.includes(compatValue);
      const haystack = normalizeSearch(`${card.dataset.search || ''} ${card.textContent || ''}`);
      const matchText = !terms.length || terms.every((term) => haystack.includes(term));
      const show = matchFilter && matchPrinter && matchText;
      card.hidden = !show;
      if (show) visible += 1;
    });
    if (empty) empty.hidden = visible > 0;
    if (activeSummary) {
      const chip = document.querySelector(`[data-material-filter="${selectedFilter}"]`);
      const compatLabel = compatFilter?.selectedOptions?.[0]?.textContent || 'All materials';
      activeSummary.textContent = `Showing ${visible} material${visible === 1 ? '' : 's'} for ${compatLabel}${chip && selectedFilter !== 'all' ? ` with ${chip.textContent} filter` : ''}.`;
    }
  };
  search?.addEventListener('input', updateMaterials);
  compatFilter?.addEventListener('change', updateMaterials);
  document.querySelectorAll('[data-material-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedFilter = button.dataset.materialFilter;
      document.querySelectorAll('[data-material-filter]').forEach((candidate) => candidate.classList.remove('is-selected'));
      button.classList.add('is-selected');
      updateMaterials();
    });
  });
  filterReset?.addEventListener('click', () => {
    if (search) search.value = '';
    if (compatFilter) compatFilter.value = 'all';
    selectedFilter = 'all';
    document.querySelectorAll('[data-material-filter]').forEach((candidate) => candidate.classList.toggle('is-selected', candidate.dataset.materialFilter === 'all'));
    updateMaterials();
  });
  if (!document.querySelector('[data-material-filter]')) {
    document.querySelectorAll('#family-filters .chip[data-family]').forEach((button) => {
      button.addEventListener('click', () => {
        selectedFilter = button.dataset.family === 'all' ? 'all' : `family:${button.dataset.family}`;
        document.querySelectorAll('#family-filters .chip[data-family]').forEach((candidate) => candidate.classList.remove('is-selected'));
        button.classList.add('is-selected');
        updateMaterials();
      });
    });
  }
  updateMaterials();
})();
