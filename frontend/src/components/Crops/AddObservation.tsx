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
  Box,
  Image,
} from "@chakra-ui/react";
import { useState } from "react";
import { FiPlus, FiUpload } from "react-icons/fi";

import { 
  CropsService,
  ZonesService,
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

interface ObservationFormData {
  notes: string;
  height_cm: number | undefined;
  health_score: number | undefined;
}

const AddObservation = ({ zone }: AddObservationProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  // First check if the zone has a crop
  const { data: hasCrop } = useQuery({
    queryKey: ["zone-has-crop", zone.id],
    queryFn: () => ZonesService.hasCrop({ 
      zoneId: zone.id 
    }),
    enabled: isOpen,
    retry: false,
    staleTime: 0,
  });

  // Get the active zone crop to get the zone_crop_id (only if we know there's a crop)
  const { data: zoneCrop } = useQuery({
    queryKey: ["zone-crop", zone.id],
    queryFn: () => CropsService.getZoneCrop({ zoneId: zone.id }),
    enabled: isOpen && hasCrop === true, // Only fetch if dialog is open and zone has crop
    retry: false, // Don't retry on 404
    staleTime: 0, // Always fetch fresh data
    throwOnError: false, // Handle errors gracefully
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ObservationFormData>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      notes: "",
      height_cm: undefined,
      health_score: undefined,
    },
  });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setSelectedFile(file);
    
    // Create preview URL
    if (file) {
      const url = URL.createObjectURL(file);
      setPreviewUrl(url);
    } else {
      setPreviewUrl(null);
    }
  };

  const mutation = useMutation({
    mutationFn: async (formData: FormData) => {
      // Create a custom fetch request for multipart data
      const token = localStorage.getItem('access_token');
      
      // Log what we're sending for debugging
      console.log("Sending FormData with entries:");
      for (const [key, value] of formData.entries()) {
        console.log(`${key}:`, value);
      }
      
      const response = await fetch(`/api/v1/crops/zones/${zone.id}/observations/`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error("Response status:", response.status);
        console.error("Response body:", errorText);
        throw new Error(`Failed to create observation: ${response.status} - ${errorText}`);
      }
      
      return response.json();
    },
    onSuccess: () => {
      showSuccessToast("Observation added successfully.");
      reset();
      setSelectedFile(null);
      setPreviewUrl(null);
      setIsOpen(false);
    },
    onError: (err: Error) => {
      console.error("Observation creation error:", err);
      handleError(err as ApiError);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["crop-observations", zone.id] });
    },
  });

  const onSubmit: SubmitHandler<ObservationFormData> = (data) => {
    console.log("Form data received:", data);
    
    if (!zoneCrop?.id) {
      console.error("No zone crop ID available");
      return;
    }
    
    // Create FormData for multipart upload
    const formData = new FormData();
    
    // Add form fields only if they have values - be more explicit about types
    if (data.notes && data.notes.trim()) {
      formData.append('notes', data.notes.trim());
    }
    if (data.height_cm !== undefined && data.height_cm !== null && !isNaN(data.height_cm)) {
      formData.append('height_cm', data.height_cm.toString());
    }
    if (data.health_score !== undefined && data.health_score !== null && !isNaN(data.health_score)) {
      formData.append('health_score', data.health_score.toString());
    }
    
    // Add file if selected
    if (selectedFile) {
      formData.append('file', selectedFile);
    }
    
    console.log("FormData prepared with file:", selectedFile?.name);
    mutation.mutate(formData);
  };

  const resetForm = () => {
    reset();
    setSelectedFile(null);
    setPreviewUrl(null);
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
  };

  // Don't show the button if zone doesn't have a crop
  if (hasCrop === false) {
    return null;
  }

  // Don't show the button if we can't get zone crop data or if there's an error
  if (!zoneCrop) {
    return null;
  }

  return (
    <DialogRoot
      size={{ base: "sm", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => {
        setIsOpen(open);
        if (!open) {
          resetForm();
        }
      }}
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

              <Field label="Image (Optional)">
                <Input
                  type="file"
                  accept="image/*"
                  onChange={handleFileChange}
                  size="sm"
                />
                {selectedFile && (
                  <Text fontSize="sm" color="gray.600" mt={1}>
                    Selected: {selectedFile.name}
                  </Text>
                )}
              </Field>

              {previewUrl && (
                <Box>
                  <Text fontSize="sm" fontWeight="medium" mb={2} color="gray.700">
                    Image Preview
                  </Text>
                  <Image
                    src={previewUrl}
                    alt="Preview"
                    maxW="200px"
                    maxH="150px"
                    objectFit="cover"
                    rounded="md"
                    border="1px"
                    borderColor="gray.200"
                  />
                </Box>
              )}
            </VStack>
          </DialogBody>

          <DialogFooter gap={2}>
            <DialogActionTrigger asChild>
              <Button
                variant="subtle"
                colorPalette="gray"
                disabled={isSubmitting}
                onClick={resetForm}
              >
                Cancel
              </Button>
            </DialogActionTrigger>
            <Button
              variant="solid"
              type="submit"
              loading={isSubmitting}
            >
              <FiUpload fontSize="14px" />
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
