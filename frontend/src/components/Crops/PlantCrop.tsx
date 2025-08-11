import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitHandler, useForm } from "react-hook-form";
import { useEffect } from "react";

import {
  Button,
  DialogActionTrigger,
  DialogTitle,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useState } from "react";
import { FiPlus } from "react-icons/fi";

import { 
  type ZoneCropCreate, 
  CropsService, 
  type CropPublic, 
  type ZonePublic 
} from "@/client";
import type { ApiError } from "@/client/core/ApiError";
import useCustomToast from "@/hooks/useCustomToast";
import { handleError } from "@/utils";
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogRoot,
  DialogTrigger,
} from "../ui/dialog";
import { Field } from "../ui/field";

interface PlantCropProps {
  zone: ZonePublic;
}

const PlantCrop = ({ zone }: PlantCropProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  // Hook to refresh the page when a crop is planted
  useEffect(() => {
    if (!isOpen) {
      queryClient.invalidateQueries({ queryKey: ["zones"] });
      queryClient.invalidateQueries({ queryKey: ["zone-crop", zone.id] });
    }
  }, [isOpen, queryClient, zone.id]);

  // Get available crop templates
  const { data: crops } = useQuery({
    queryKey: ["crops"],
    queryFn: () => CropsService.listCrops(),
    enabled: isOpen,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isValid, isSubmitting },
  } = useForm<ZoneCropCreate>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      crop_id: "",
      zone_id: zone.id,
      area_sqm: undefined,
    },
  });

  const mutation = useMutation({
    mutationFn: (data: ZoneCropCreate) =>
      CropsService.plantCropInZone({ 
        zoneId: zone.id, 
        requestBody: data 
      }),
    onSuccess: () => {
      showSuccessToast("Crop planted successfully.");
      reset();
      setIsOpen(false);
    },
    onError: (err: ApiError) => {
      handleError(err);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["zones"] });
      queryClient.invalidateQueries({ queryKey: ["zone-crop", zone.id] });
    },
  });

  const onSubmit: SubmitHandler<ZoneCropCreate> = (data) => {
    mutation.mutate({ ...data, zone_id: zone.id });
  };

  return (
    <DialogRoot
      size={{ base: "sm", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button size="sm" colorPalette="green">
          <FiPlus fontSize="12px" />
          Plant Crop
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Plant Crop in Zone {zone.zone_number}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Select a crop to plant in this zone.</Text>
            <VStack gap={4}>
              <Field
                required
                invalid={!!errors.crop_id}
                errorText={errors.crop_id?.message}
                label="Crop Template"
              >
                <select 
                  id="crop_id" 
                  {...register("crop_id", { required: "Please select a crop." })}
                >
                  <option value="">Select a crop...</option>
                  {crops?.map((crop: CropPublic) => (
                    <option key={crop.id} value={crop.id}>
                      {crop.name}
                    </option>
                  ))}
                </select>
              </Field>

              <Field
                invalid={!!errors.area_sqm}
                errorText={errors.area_sqm?.message}
                label="Area (sq meters)"
              >
                <input
                  id="area_sqm"
                  type="number"
                  step="0.1"
                  {...register("area_sqm", { valueAsNumber: true })}
                  placeholder="Optional area in square meters"
                />
              </Field>
            </VStack>
          </DialogBody>

          <DialogFooter gap={2}>
            <DialogActionTrigger asChild>
              <Button
                variant="subtle"
                colorPalette="gray"
                disabled={isSubmitting}
              >
                Cancel
              </Button>
            </DialogActionTrigger>
            <Button
              variant="solid"
              type="submit"
              disabled={!isValid}
              loading={isSubmitting}
            >
              Plant Crop
            </Button>
          </DialogFooter>
        </form>
        <DialogCloseTrigger />
      </DialogContent>
    </DialogRoot>
  );
};

export default PlantCrop;
