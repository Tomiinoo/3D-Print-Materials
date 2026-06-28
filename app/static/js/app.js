(() => {
  const sidebar = document.getElementById('sidebar');
  document.querySelector('[data-sidebar-toggle]')?.addEventListener('click', () => sidebar?.classList.toggle('is-open'));

  document.querySelectorAll('[data-toggle]').forEach((trigger) => {
    trigger.addEventListener('click', () => {
      const target = document.getElementById(trigger.dataset.toggle);
      if (target) target.hidden = !target.hidden;
    });
  });

  document.querySelectorAll('input[type="date"]').forEach((input) => {
    if (!input.value) input.value = new Date().toISOString().slice(0, 10);
  });

  const search = document.getElementById('material-search');
  const cards = [...document.querySelectorAll('#material-grid .material-card')];
  const empty = document.getElementById('material-empty');
  let selectedFamily = 'all';
  const updateMaterials = () => {
    const term = (search?.value || '').trim().toLowerCase();
    let visible = 0;
    cards.forEach((card) => {
      const matchFamily = selectedFamily === 'all' || card.dataset.family === selectedFamily;
      const matchText = !term || card.dataset.search.toLowerCase().includes(term);
      const show = matchFamily && matchText;
      card.hidden = !show;
      if (show) visible += 1;
    });
    if (empty) empty.hidden = visible > 0;
  };
  search?.addEventListener('input', updateMaterials);
  document.querySelectorAll('[data-family]').forEach((button) => {
    button.addEventListener('click', () => {
      selectedFamily = button.dataset.family;
      document.querySelectorAll('[data-family]').forEach((candidate) => candidate.classList.remove('is-selected'));
      button.classList.add('is-selected');
      updateMaterials();
    });
  });
})();
