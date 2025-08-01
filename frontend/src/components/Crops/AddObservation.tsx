import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitHandler, useForm } from "react-hook-form";

import {
  Button,
  DialogActionTrigger,
  DialogTitle,
  Input,
  Textarea,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useState } from "react";
import { FiPlus } from "react-icons/fi";

import { 
  type ZoneCropObservationCreate, 
  CropsService, 
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

interface AddObservationProps {
  zone: ZonePublic;
}

const AddObservation = ({ zone }: AddObservationProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  // Get the active zone crop to get the zone_crop_id
  const { data: zoneCrop } = useQuery({
    queryKey: ["zone-crop", zone.id],
    queryFn: () => CropsService.getZoneCrop({ zoneId: zone.id }),
    enabled: isOpen,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Omit<ZoneCropObservationCreate, 'zone_crop_id'>>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      notes: "",
      height_cm: undefined,
      health_score: undefined,
      image_url: "",
    },
  });

  const mutation = useMutation({
    mutationFn: (data: ZoneCropObservationCreate) => {
      console.log("Sending observation data:", data); // Debug log
      return CropsService.createZoneCropObservation({ 
        zoneId: zone.id, 
        requestBody: data
      });
    },
    onSuccess: () => {
      showSuccessToast("Observation added successfully.");
      reset();
      setIsOpen(false);
    },
    onError: (err: ApiError) => {
      console.error("Observation creation error:", err); // Debug log
      handleError(err);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["crop-observations", zone.id] });
    },
  });

  const onSubmit: SubmitHandler<Omit<ZoneCropObservationCreate, 'zone_crop_id'>> = (data) => {
    console.log("Form data received:", data); // Debug log
    
    if (!zoneCrop?.id) {
      console.error("No zone crop ID available");
      return;
    }
    
    // Clean up the data and include zone_crop_id
    const cleanedData: ZoneCropObservationCreate = {
      zone_crop_id: zoneCrop.id, // Include the required zone_crop_id
      notes: data.notes?.trim() || undefined,
      height_cm: data.height_cm || undefined, 
      health_score: data.health_score || undefined,
      image_url: data.image_url?.trim() || undefined,
    };
    
    console.log("Cleaned data:", cleanedData); // Debug log
    mutation.mutate(cleanedData);
  };

  // Don't show the form if we don't have a zone crop
  if (!zoneCrop) {
    return null;
  }

  return (
    <DialogRoot
      size={{ base: "sm", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button size="sm" colorPalette="blue">
          <FiPlus fontSize="12px" />
          Add Observation
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Add Crop Observation</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Record an observation for the crop in Zone {zone.zone_number}.</Text>
            <VStack gap={4}>
              <Field
                invalid={!!errors.notes}
                errorText={errors.notes?.message}
                label="Notes (Optional)"
              >
                <Textarea
                  id="notes"
                  {...register("notes")}
                  placeholder="Observations about the crop..."
                  rows={3}
                />
              </Field>

              <Field
                invalid={!!errors.height_cm}
                errorText={errors.height_cm?.message}
                label="Height (cm) - Optional"
              >
                <Input
                  id="height_cm"
                  type="number"
                  step="0.1"
                  min="0"
                  {...register("height_cm", { 
                    valueAsNumber: true,
                    setValueAs: (value) => value === "" ? undefined : Number(value)
                  })}
                  placeholder="Plant height in centimeters"
                />
              </Field>

              <Field
                invalid={!!errors.health_score}
                errorText={errors.health_score?.message}
                label="Health Score (1-10) - Optional"
              >
                <Input
                  id="health_score"
                  type="number"
                  min="1"
                  max="10"
                  {...register("health_score", { 
                    valueAsNumber: true,
                    setValueAs: (value) => value === "" ? undefined : Number(value),
                    min: { value: 1, message: "Minimum score is 1" },
                    max: { value: 10, message: "Maximum score is 10" }
                  })}
                  placeholder="Rate plant health from 1-10"
                />
              </Field>

              <Field
                invalid={!!errors.image_url}
                errorText={errors.image_url?.message}
                label="Image URL (Optional)"
              >
                <Input
                  id="image_url"
                  {...register("image_url")}
                  placeholder="Optional image URL"
                  type="url"
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
              loading={isSubmitting}
            >
              Add Observation
            </Button>
          </DialogFooter>
        </form>
        <DialogCloseTrigger />
      </DialogContent>
    </DialogRoot>
  );
};

export default AddObservation;
