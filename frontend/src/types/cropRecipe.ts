export interface CropRecipe {
  name: string;
  species: string;
  growth_duration_days: number;
  ideal_conditions: {
    temperature_C: { min: number; max: number };
    'humidity_%': { min: number; max: number };
    vpd_kPa: { min: number; max: number };
    light_hours: number;
    ppfd_umol_m2_s: { min: number; max: number };
    dli_mol_m2_day: { min: number; max: number };
    co2_ppm: { min: number; max: number };
    nutrient_ec_dS_m: { min: number; max: number };
    nutrient_pH: { min: number; max: number };
  };
  stages: Array<{
    name: string;
    duration_days: { start_day: number; end_day: number };
    conditions: {
      temperature_C: { min: number; max: number };
      'humidity_%': { min: number; max: number };
      vpd_kPa: { min: number; max: number };
      light_hours: number;
      ppfd_umol_m2_s?: { min: number; max: number };
      nutrient_ec_dS_m?: { min: number; max: number };
      water_ml_per_plant_day?: number;
    };
    tasks: string[];
    health_metrics: {
      healthy: string;
      red_flags: string;
    };
  }>;
  expected_yield_kg: { min: number; max: number };
}

// Type guard to check if recipe has the expected structure
export const isCropRecipe = (recipe: any): recipe is CropRecipe => {
  return recipe &&
    typeof recipe === 'object' &&
    typeof recipe.growth_duration_days === 'number' &&
    Array.isArray(recipe.stages) &&
    recipe.expected_yield_kg &&
    typeof recipe.expected_yield_kg.min === 'number';
};
