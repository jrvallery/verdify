import { useMemo } from "react";
import { ZoneCropPublic, CropPublic, ZoneCropObservationPublic } from "@/client";
import { isCropRecipe } from "@/types/cropRecipe";

export const useCropStageData = (
  zoneCrop: ZoneCropPublic | undefined,
  crop: CropPublic | undefined,
  observations: ZoneCropObservationPublic[] | undefined
) => {
  return useMemo(() => {
    const getDaysGrowing = () => {
      if (!zoneCrop?.start_date) return 0;

      const startDate = new Date(zoneCrop.start_date);
      const endDate = zoneCrop.end_date ? new Date(zoneCrop.end_date) : new Date();
      const diffTime = Math.abs(endDate.getTime() - startDate.getTime());
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      return diffDays;
    };

    const getCurrentStage = () => {
      if (!zoneCrop?.start_date || !crop?.recipe || !isCropRecipe(crop.recipe)) return null;

      const daysGrown = getDaysGrowing();
      return crop.recipe.stages.find((stage) =>
        daysGrown >= stage.duration_days.start_day && daysGrown <= stage.duration_days.end_day
      );
    };

    const getNextStage = () => {
      if (!zoneCrop?.start_date || !crop?.recipe || !isCropRecipe(crop.recipe)) return null;

      const daysGrown = getDaysGrowing();
      return crop.recipe.stages.find((stage) =>
        daysGrown < stage.duration_days.start_day
      );
    };

    const getDaysUntilNextStage = () => {
      const nextStage = getNextStage();
      if (!nextStage) return null;

      const daysGrown = getDaysGrowing();
      return nextStage.duration_days.start_day - daysGrown;
    };

    const getGrowthProgress = () => {
      if (!crop?.recipe || !isCropRecipe(crop.recipe) || !zoneCrop?.start_date) return 0;

      const daysGrown = getDaysGrowing();
      const progress = (daysGrown / crop.recipe.growth_duration_days) * 100;
      return Math.min(progress, 100);
    };

    const getLatestObservation = () => {
      if (!observations || observations.length === 0) return null;
      return observations.sort((a, b) =>
        new Date(b.observed_at || 0).getTime() - new Date(a.observed_at || 0).getTime()
      )[0];
    };

    const getCurrentTasks = () => {
      const currentStage = getCurrentStage();
      return currentStage?.tasks || [];
    };

    const getExpectedYield = () => {
      if (!crop?.recipe || !isCropRecipe(crop.recipe)) return null;
      const { min, max } = crop.recipe.expected_yield_kg;
      return `${min}-${max} kg`;
    };

    const daysGrowing = getDaysGrowing();
    const currentStage = getCurrentStage();
    const nextStage = getNextStage();
    const daysUntilNext = getDaysUntilNextStage();
    const progress = getGrowthProgress();
    const latestObs = getLatestObservation();
    const currentTasks = getCurrentTasks();
    const expectedYield = getExpectedYield();

    return {
      daysGrowing,
      currentStage,
      nextStage,
      daysUntilNext,
      progress,
      latestObs,
      currentTasks,
      expectedYield,
      getDaysGrowing,
      getCurrentStage,
      getNextStage,
      getDaysUntilNextStage,
      getGrowthProgress,
      getLatestObservation,
      getCurrentTasks,
      getExpectedYield
    };
  }, [zoneCrop, crop, observations]);
};
