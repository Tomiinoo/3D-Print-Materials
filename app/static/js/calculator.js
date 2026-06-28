(() => {
  const data = document.getElementById('calculator-products-data');
  if (!data) return;
  const products = JSON.parse(data.textContent);
  const form = document.getElementById('calculator-form');
  const select = document.getElementById('calc-product');
  const info = document.getElementById('calculator-product-info');
  const euro = (value) => value === null || value === undefined ? 'No price recorded' : `€${Number(value).toFixed(2)}`;
  const grams = (value) => value === null || value === undefined ? '—' : `${Number(value).toFixed(1)} g`;

  const updateInfo = () => {
    const product = products.find((entry) => String(entry.id) === select.value);
    if (!product) return;
    info.textContent = `${product.material_name} · density ${Number(product.density_g_cm3).toFixed(2)} g/cm³ · ${euro(product.price_per_kg)}${product.price_per_kg ? '/kg' : ''} · ${product.spool_weight_g} g spool`;
  };
  select.addEventListener('change', updateInfo);
  updateInfo();

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const params = new URLSearchParams(new FormData(form));
    try {
      const response = await fetch(`/api/calculate?${params.toString()}`);
      if (!response.ok) throw new Error('Calculation failed');
      const result = await response.json();
      document.getElementById('result-total').textContent = result.total_cost_eur === null ? 'No price' : euro(result.total_cost_eur);
      document.getElementById('result-product').textContent = `${result.product} · ${result.material}`;
      document.getElementById('result-part').textContent = grams(result.part_mass_g);
      document.getElementById('result-support').textContent = grams(result.support_mass_g);
      document.getElementById('result-total-mass').textContent = grams(result.total_mass_g);
      document.getElementById('result-price-per-kg').textContent = result.price_per_kg === null ? 'Add price' : `${euro(result.price_per_kg)}/kg`;
      document.getElementById('result-material-cost').textContent = result.material_cost_eur === null ? 'Add price' : euro(result.material_cost_eur);
      document.getElementById('result-energy-cost').textContent = euro(result.energy_cost_eur);
    } catch (error) {
      document.getElementById('result-product').textContent = `Could not calculate: ${error.message}`;
    }
  });
})();
