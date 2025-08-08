import { useQuery } from "@tanstack/react-query";
import { ZonesService, CropsService, ZonePublic } from "@/client";

export const useCropQueries = (zone: ZonePublic) => {
  // Check if zone has a crop
  const { data: hasCrop, isLoading: checkingCrop } = useQuery({
    queryKey: ["zone-has-crop", zone.id],
    queryFn: () => ZonesService.hasCrop({ zoneId: zone.id }),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });

  // Get zone crop data
  const { data: zoneCrop, isLoading: cropLoading } = useQuery({
    queryKey: ["zone-crop", zone.id],
    queryFn: () => CropsService.getZoneCrop({ zoneId: zone.id }),
    enabled: hasCrop === true,
    retry: false,
    staleTime: 0,
    gcTime: 0,
  });

  // Get crop template details
  const { data: crop } = useQuery({
    queryKey: ["crop", zoneCrop?.crop_id],
    queryFn: () => CropsService.getCrop({ cropId: zoneCrop!.crop_id }),
    enabled: !!zoneCrop?.crop_id,
    staleTime: 5 * 60 * 1000,
  });

  // Get observations
  const { data: observations } = useQuery({
    queryKey: ["crop-observations", zone.id],
    queryFn: () => CropsService.listZoneCropObservations({ zoneId: zone.id }),
    enabled: !!zoneCrop && zoneCrop.is_active,
    throwOnError: false,
  });

  const isLoading = checkingCrop || (hasCrop && cropLoading);
  const hasNoCrop = hasCrop === false || !zoneCrop;

  return {
    hasCrop,
    zoneCrop,
    crop,
    observations,
    isLoading,
    hasNoCrop,
    checkingCrop,
    cropLoading
  };
};
