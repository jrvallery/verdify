import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SubmitHandler, useForm } from "react-hook-form";

import {
  Button,
  DialogActionTrigger,
  DialogTitle,
  Input,
  Text,
  VStack,
} from "@chakra-ui/react";
import { useState } from "react";
import { FaPlus } from "react-icons/fa";

import { type ZoneCreate, LocationEnum, ZonesService } from "@/client";
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

interface AddZoneProps {
  greenhouseId: string;
}

const AddZone = ({ greenhouseId }: AddZoneProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isValid, isSubmitting },
  } = useForm<ZoneCreate>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      zone_number: 1,
      location: "N" as LocationEnum,
      temperature: undefined,
      humidity: undefined,
      greenhouse_id: greenhouseId,
    },
  });

  const mutation = useMutation({
    mutationFn: (data: ZoneCreate) =>
        ZonesService.createZone({ greenhouseId, requestBody: data } as any),
    onSuccess: () => {
      showSuccessToast("Zone created successfully.");
      reset();
      setIsOpen(false);
    },
    onError: (err: ApiError) => {
      handleError(err);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["zones"] });
    },
  });

  const onSubmit: SubmitHandler<ZoneCreate> = (data) => {
    mutation.mutate({ ...data, greenhouse_id: greenhouseId });
  };

  const locations = [
    { value: "N", label: "North" },
    { value: "NE", label: "Northeast" },
    { value: "E", label: "East" },
    { value: "SE", label: "Southeast" },
    { value: "S", label: "South" },
    { value: "SW", label: "Southwest" },
    { value: "W", label: "West" },
    { value: "NW", label: "Northwest" },
  ];

  return (
    <DialogRoot
      size={{ base: "xs", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button value="add-zone" my={4}>
          <FaPlus fontSize="16px" />
          Add Zone
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Add Zone</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Fill in the details to add a new zone.</Text>
            <VStack gap={4}>
              <Field
                required
                invalid={!!errors.zone_number}
                errorText={errors.zone_number?.message}
                label="Zone Number"
              >
                <Input
                  id="zone_number"
                  type="number"
                  {...register("zone_number", {
                    required: "Zone number is required.",
                    valueAsNumber: true,
                    min: { value: 1, message: "Zone number must be at least 1" }
                  })}
                  placeholder="1"
                />
              </Field>

              <Field
                required
                invalid={!!errors.location}
                errorText={errors.location?.message}
                label="Location"
              >
                <select 
                  id="location" 
                  {...register("location", { required: "Location is required." })}
                >
                  {locations.map((location) => (
                    <option key={location.value} value={location.value}>
                      {location.label}
                    </option>
                  ))}
                </select>
              </Field>

              <Field
                invalid={!!errors.temperature}
                errorText={errors.temperature?.message}
                label="Initial Temperature (°C)"
              >
                <Input
                  id="temperature"
                  type="number"
                  step="any"
                  {...register("temperature", { valueAsNumber: true })}
                  placeholder="Optional"
                />
              </Field>

              <Field
                invalid={!!errors.humidity}
                errorText={errors.humidity?.message}
                label="Initial Humidity (%)"
              >
                <Input
                  id="humidity"
                  type="number"
                  step="any"
                  {...register("humidity", { valueAsNumber: true })}
                  placeholder="Optional"
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
              Save
            </Button>
          </DialogFooter>
        </form>
        <DialogCloseTrigger />
      </DialogContent>
    </DialogRoot>
  );
};

export default AddZone;
