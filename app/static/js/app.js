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

  const search = document.getElementById('material-search');
  const cards = [...document.querySelectorAll('#material-grid .material-card, #catalog-grid .material-card')];
  const empty = document.getElementById('material-empty');
  let selectedFilter = 'all';
  const normalizeSearch = (value) => String(value ?? '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
  const updateMaterials = () => {
    const terms = normalizeSearch(search?.value || '').split(/\s+/).filter(Boolean);
    let visible = 0;
    cards.forEach((card) => {
      const filters = (card.dataset.filters || '').split(/\s+/).filter(Boolean);
      const matchFilter = selectedFilter === 'all'
        || (selectedFilter.startsWith('family:') && card.dataset.family === selectedFilter.slice(7))
        || filters.includes(selectedFilter);
      const haystack = normalizeSearch(`${card.dataset.search || ''} ${card.textContent || ''}`);
      const matchText = !terms.length || terms.every((term) => haystack.includes(term));
      const show = matchFilter && matchText;
      card.hidden = !show;
      if (show) visible += 1;
    });
    if (empty) empty.hidden = visible > 0;
  };
  search?.addEventListener('input', updateMaterials);
  document.querySelectorAll('[data-material-filter]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedFilter = button.dataset.materialFilter;
      document.querySelectorAll('[data-material-filter]').forEach((candidate) => candidate.classList.remove('is-selected'));
      button.classList.add('is-selected');
      updateMaterials();
    });
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
