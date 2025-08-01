import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SubmitHandler, useForm } from "react-hook-form";
import { useParams } from "@tanstack/react-router";

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

import { type SensorCreate, SensorType, SensorsService } from "@/client";
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

interface AddSensorProps {
  controllerId: string;
}

const AddSensor = ({ controllerId }: AddSensorProps) => {
  const { greenhouseId } = useParams({ from: "/greenhouses/$greenhouseId" });
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isValid, isSubmitting },
  } = useForm<SensorCreate>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      name: "",
      type: "temperature" as SensorType,
      model: "",
      value: 0,
      unit: "",
      is_mapped: false,
      controller_id: controllerId,
    },
  });

  const mutation = useMutation({
    mutationFn: (data: SensorCreate) =>
      SensorsService.createSensor({ 
        controllerId,
        greenhouseId,
        requestBody: data 
      } as any),
    onSuccess: () => {
      showSuccessToast("Sensor created successfully.");
      reset();
      setIsOpen(false);
    },
    onError: (err: ApiError) => {
      handleError(err);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["sensors", controllerId] });
    },
  });

  const onSubmit: SubmitHandler<SensorCreate> = (data) => {
    mutation.mutate({ ...data, controller_id: controllerId });
  };

  return (
    <DialogRoot
      size={{ base: "xs", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button value="add-sensor" size="sm">
          <FaPlus fontSize="12px" />
          Add Sensor
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Add Sensor</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Fill in the details to add a new sensor.</Text>
            <VStack gap={4}>
              <Field
                required
                invalid={!!errors.name}
                errorText={errors.name?.message}
                label="Name"
              >
                <Input
                  id="name"
                  {...register("name", {
                    required: "Name is required.",
                  })}
                  placeholder="Sensor name"
                  type="text"
                />
              </Field>

              <Field
                required
                invalid={!!errors.type}
                errorText={errors.type?.message}
                label="Type"
              >
                <select id="type" {...register("type", { required: "Type is required." })}>
                  <option value="temperature">Temperature</option>
                  <option value="humidity">Humidity</option>
                  <option value="co2">CO2</option>
                  <option value="light">Light</option>
                  <option value="soil_moisture">Soil Moisture</option>
                </select>
              </Field>

              <Field
                invalid={!!errors.model}
                errorText={errors.model?.message}
                label="Model"
              >
                <Input
                  id="model"
                  {...register("model")}
                  placeholder="Sensor model (optional)"
                  type="text"
                />
              </Field>

              <Field
                invalid={!!errors.value}
                errorText={errors.value?.message}
                label="Initial Value"
              >
                <Input
                  id="value"
                  type="number"
                  step="any"
                  {...register("value", { valueAsNumber: true })}
                  placeholder="0"
                />
              </Field>

              <Field
                invalid={!!errors.unit}
                errorText={errors.unit?.message}
                label="Unit"
              >
                <Input
                  id="unit"
                  {...register("unit")}
                  placeholder="e.g., °C, %, ppm"
                  type="text"
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

export default AddSensor;
