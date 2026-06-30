(() => {
  const data = document.getElementById('calculator-products-data');
  if (!data) return;

  const products = JSON.parse(data.textContent);
  const form = document.getElementById('calculator-form');
  const select = document.getElementById('calc-product');
  const info = document.getElementById('calculator-product-info');
  const modeInputs = [...document.querySelectorAll('input[name="calc_mode"]')];
  const volumeGroups = [...document.querySelectorAll('[data-calc-volume]')];
  const gramsGroups = [...document.querySelectorAll('[data-calc-grams]')];
  const remainingNote = document.getElementById('result-remaining-note');
  const euro = (value) => value === null || value === undefined ? 'No price recorded' : `€${Number(value).toFixed(2)}`;
  const grams = (value) => value === null || value === undefined ? '-' : `${Number(value).toFixed(1)} g`;

  const selectedMode = () => modeInputs.find((input) => input.checked)?.value || 'grams';
  const selectedProduct = () => products.find((entry) => String(entry.id) === select.value);

  const setGroupState = (groups, hidden) => {
    groups.forEach((group) => {
      group.hidden = hidden;
      group.querySelectorAll('input').forEach((input) => {
        input.disabled = hidden;
        input.required = !hidden && input.id === 'calc-used-g';
      });
    });
  };

  const setMode = () => {
    const useGrams = selectedMode() === 'grams';
    setGroupState(volumeGroups, useGrams);
    setGroupState(gramsGroups, !useGrams);
  };

  const updateInfo = () => {
    const product = selectedProduct();
    if (!product) return;
    const remaining = product.remaining_g === undefined ? '' : ` / ${grams(product.remaining_g)} remaining`;
    info.textContent = `${product.material_name} / density ${Number(product.density_g_cm3).toFixed(2)} g/cm3 / ${euro(product.price_per_kg)}${product.price_per_kg ? '/kg' : ''} / ${product.spool_weight_g} g spool${remaining}`;
  };

  modeInputs.forEach((input) => input.addEventListener('change', setMode));
  select.addEventListener('change', updateInfo);
  setMode();
  updateInfo();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const params = new URLSearchParams(new FormData(form));
    params.delete('calc_mode');
    if (selectedMode() === 'grams') {
      params.delete('model_volume_mm3');
      params.delete('support_volume_mm3');
    } else {
      params.delete('used_g');
      params.delete('support_g');
    }

    try {
      const response = await fetch(`/api/calculate?${params.toString()}`);
      if (!response.ok) throw new Error('Calculation failed');
      const result = await response.json();
      document.getElementById('result-total').textContent = result.total_cost_eur === null ? 'No price' : euro(result.total_cost_eur);
      document.getElementById('result-product').textContent = `${result.product} / ${result.material}`;
      document.getElementById('result-part').textContent = grams(result.part_mass_g);
      document.getElementById('result-support').textContent = grams(result.support_mass_g);
      document.getElementById('result-purge').textContent = grams(result.purge_mass_g);
      document.getElementById('result-waste').textContent = grams(result.waste_mass_g);
      document.getElementById('result-total-mass').textContent = grams(result.total_mass_g);
      document.getElementById('result-price-per-kg').textContent = result.price_per_kg === null ? 'Add price' : `${euro(result.price_per_kg)}/kg`;
      document.getElementById('result-material-cost').textContent = result.material_cost_eur === null ? 'Add price' : euro(result.material_cost_eur);
      document.getElementById('result-energy-cost').textContent = euro(result.energy_cost_eur);

      const product = selectedProduct();
      if (product && Number.isFinite(Number(product.remaining_g))) {
        const after = Math.max(0, Number(product.remaining_g) - Number(result.total_mass_g || 0));
        remainingNote.textContent = `Estimate only: ${grams(after)} would remain on ${product.spool_code} after this print. Inventory is not changed.`;
      }
    } catch (error) {
      document.getElementById('result-product').textContent = `Could not calculate: ${error.message}`;
    }
  });
})();
