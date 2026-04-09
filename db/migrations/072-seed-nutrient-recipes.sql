-- 072: Seed nutrient_recipes with GH Flora series standard recipes
-- Idempotent: uses INSERT ON CONFLICT (name)

-- Ensure unique constraint exists for idempotent upserts
ALTER TABLE nutrient_recipes ADD CONSTRAINT IF NOT EXISTS nutrient_recipes_name_key UNIQUE (name);

INSERT INTO nutrient_recipes (name, stage, target_ec, target_ph_low, target_ph_high, n_ppm, p_ppm, k_ppm, ca_ppm, mg_ppm, fe_ppm, stock_a_ml_per_l, stock_b_ml_per_l, notes, is_active)
VALUES
  ('seedlings', 'seedling', 0.65, 5.5, 6.5,
   60, 20, 60, 40, 15, 1.5, 1.25, 1.25,
   'GH Flora series seedling rate. FloraMicro 1.25 ml/L, FloraGro 0.6 ml/L + FloraBloom 0.6 ml/L. Very light feed for germination and first true leaves.',
   true),

  ('leafy_greens_veg', 'vegetative', 1.0, 5.5, 6.5,
   120, 30, 100, 80, 30, 2.5, 2.5, 2.0,
   'GH Flora series for lettuce/herbs vegetative. FloraMicro 2.5 ml/L, FloraGro 1.5 ml/L + FloraBloom 0.5 ml/L. High nitrogen for leaf growth.',
   true),

  ('leafy_greens_mature', 'mature', 1.4, 5.5, 6.5,
   150, 40, 130, 100, 35, 3.0, 3.0, 2.5,
   'GH Flora series for lettuce/herbs mature harvest stage. FloraMicro 3.0 ml/L, FloraGro 1.5 ml/L + FloraBloom 1.0 ml/L. Balanced feed for heading/harvest.',
   true),

  ('peppers_veg', 'vegetative', 1.75, 5.5, 6.5,
   180, 45, 160, 130, 45, 3.5, 3.75, 3.25,
   'GH Flora series for peppers vegetative. FloraMicro 3.75 ml/L, FloraGro 2.5 ml/L + FloraBloom 0.75 ml/L. High N and Ca for strong stem/leaf development.',
   true),

  ('peppers_fruit', 'fruiting', 2.25, 5.5, 6.5,
   160, 70, 220, 150, 50, 4.0, 4.0, 4.75,
   'GH Flora series for peppers fruiting/ripening. FloraMicro 4.0 ml/L, FloraGro 1.0 ml/L + FloraBloom 3.75 ml/L. High K and P for fruit set and development.',
   true),

  ('strawberries', 'fruiting', 1.25, 5.5, 6.5,
   100, 40, 140, 90, 35, 3.0, 2.5, 2.75,
   'GH Flora series for strawberries. FloraMicro 2.5 ml/L, FloraGro 0.75 ml/L + FloraBloom 2.0 ml/L. Moderate feed with K emphasis for fruit quality.',
   true),

  ('herbs_general', 'vegetative', 1.2, 5.5, 6.5,
   110, 30, 110, 80, 30, 2.5, 2.5, 2.0,
   'GH Flora series for general herbs (basil, cilantro, parsley). FloraMicro 2.5 ml/L, FloraGro 1.25 ml/L + FloraBloom 0.75 ml/L. Balanced light feed for aromatic production.',
   true)

ON CONFLICT (name) DO UPDATE SET
  stage = EXCLUDED.stage,
  target_ec = EXCLUDED.target_ec,
  target_ph_low = EXCLUDED.target_ph_low,
  target_ph_high = EXCLUDED.target_ph_high,
  n_ppm = EXCLUDED.n_ppm,
  p_ppm = EXCLUDED.p_ppm,
  k_ppm = EXCLUDED.k_ppm,
  ca_ppm = EXCLUDED.ca_ppm,
  mg_ppm = EXCLUDED.mg_ppm,
  fe_ppm = EXCLUDED.fe_ppm,
  stock_a_ml_per_l = EXCLUDED.stock_a_ml_per_l,
  stock_b_ml_per_l = EXCLUDED.stock_b_ml_per_l,
  notes = EXCLUDED.notes,
  is_active = EXCLUDED.is_active;
