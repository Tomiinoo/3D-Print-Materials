(() => {
  const data = document.getElementById('calculator-products-data');
  if (!data) return;

  const products = JSON.parse(data.textContent);
  const form = document.getElementById('calculator-form');
  const select = document.getElementById('calc-product');
  const info = document.getElementById('calculator-product-info');
  const modeInputs = [...document.querySelectorAll('input[name="calc_mode"]')];
  const volumeGroups = [...document.querySelectorAll('[data-calc-volume]')];
  const gramsGroup = document.querySelector('[data-calc-grams]');
  const gramsInput = document.getElementById('calc-used-g');
  const euro = (value) => value === null || value === undefined ? 'No price recorded' : `€${Number(value).toFixed(2)}`;
  const grams = (value) => value === null || value === undefined ? '—' : `${Number(value).toFixed(1)} g`;

  const selectedMode = () => modeInputs.find((input) => input.checked)?.value || 'volume';

  const setMode = () => {
    const useGrams = selectedMode() === 'grams';
    volumeGroups.forEach((group) => {
      group.hidden = useGrams;
      group.querySelectorAll('input').forEach((input) => {
        input.disabled = useGrams;
      });
    });
    if (gramsGroup && gramsInput) {
      gramsGroup.hidden = !useGrams;
      gramsInput.disabled = !useGrams;
      gramsInput.required = useGrams;
    }
  };

  const updateInfo = () => {
    const product = products.find((entry) => String(entry.id) === select.value);
    if (!product) return;
    const remaining = product.remaining_g === undefined ? '' : ` · ${grams(product.remaining_g)} left`;
    info.textContent = `${product.material_name} · density ${Number(product.density_g_cm3).toFixed(2)} g/cm³ · ${euro(product.price_per_kg)}${product.price_per_kg ? '/kg' : ''} · ${product.spool_weight_g} g spool${remaining}`;
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
      params.delete('purge_g');
      params.delete('waste_percent');
    } else {
      params.delete('used_g');
    }

    try {
      const response = await fetch(`/api/calculate?${params.toString()}`);
      if (!response.ok) throw new Error('Calculation failed');
      const result = await response.json();
      document.getElementById('result-total').textContent = result.total_cost_eur === null ? 'No price' : euro(result.total_cost_eur);
      document.getElementById('result-product').textContent = `${result.product} · ${result.material}`;
      document.getElementById('result-part').textContent = selectedMode() === 'grams' ? grams(result.total_mass_g) : grams(result.part_mass_g);
      document.getElementById('result-support').textContent = selectedMode() === 'grams' ? '—' : grams(result.support_mass_g);
      document.getElementById('result-total-mass').textContent = grams(result.total_mass_g);
      document.getElementById('result-price-per-kg').textContent = result.price_per_kg === null ? 'Add price' : `${euro(result.price_per_kg)}/kg`;
      document.getElementById('result-material-cost').textContent = result.material_cost_eur === null ? 'Add price' : euro(result.material_cost_eur);
      document.getElementById('result-energy-cost').textContent = euro(result.energy_cost_eur);
    } catch (error) {
      document.getElementById('result-product').textContent = `Could not calculate: ${error.message}`;
    }
  });
})();
