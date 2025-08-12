import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SubmitHandler, useForm } from "react-hook-form";

import {
  Button,
  DialogActionTrigger,
  DialogTitle,
  Input,
  Text,
  VStack,
  Box,
  Flex,
} from "@chakra-ui/react";
import { useState } from "react";
import { FaPlus } from "react-icons/fa";

import { type GreenhouseCreate, GreenhousesService } from "@/client";
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
import { LocationMap } from "@/components/Common/LocationMap";

const AddGreenhouse = () => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isValid, isSubmitting },
    setValue,
    watch,
  } = useForm<GreenhouseCreate>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      title: "",
      description: "",
      latitude: undefined as unknown as number | undefined,
      longitude: undefined as unknown as number | undefined,
    },
  });

  const lat = watch("latitude");
  const lng = watch("longitude");

  const mutation = useMutation({
    mutationFn: (data: GreenhouseCreate) =>
      GreenhousesService.createGreenhouse({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("Greenhouse created successfully.");
      reset();
      setIsOpen(false);
    },
    onError: (err: ApiError) => {
      handleError(err);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["greenhouses"] });
    },
  });

  const onSubmit: SubmitHandler<GreenhouseCreate> = (data) => {
    const payload: GreenhouseCreate = {
      title: data.title,
      description: data.description,
      latitude: Number.isFinite(data.latitude as any) ? data.latitude : undefined,
      longitude: Number.isFinite(data.longitude as any) ? data.longitude : undefined,
    } as GreenhouseCreate;
    mutation.mutate(payload);
  };

  return (
    <DialogRoot
      size={{ base: "xs", md: "md" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button value="add-greenhouse" my={4}>
          <FaPlus fontSize="16px" />
          Add Greenhouse
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Add Greenhouse</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>Fill in the details to add a new greenhouse.</Text>
            <VStack gap={4}>
              <Field
                required
                invalid={!!errors.title}
                errorText={errors.title?.message}
                label="Title"
              >
                <Input
                  id="title"
                  {...register("title", {
                    required: "Title is required.",
                  })}
                  placeholder="Title"
                  type="text"
                />
              </Field>

              <Field
                invalid={!!errors.description}
                errorText={errors.description?.message}
                label="Description"
              >
                <Input
                  id="description"
                  {...register("description")}
                  placeholder="Description"
                  type="text"
                />
              </Field>

              <Box w="full">
                <Text mb={2} fontWeight="medium">Location</Text>
                <LocationMap
                  lat={lat ?? undefined}
                  lng={lng ?? undefined}
                  onChange={(newLat, newLng) => {
                    setValue("latitude", newLat, { shouldDirty: true, shouldValidate: true });
                    setValue("longitude", newLng, { shouldDirty: true, shouldValidate: true });
                  }}
                  height={280}
                />
                <Flex gap={3} mt={3} wrap="wrap">
                  <Input
                    placeholder="Latitude"
                    type="number"
                    step="any"
                    width="xs"
                    {...register("latitude", {
                      setValueAs: (v) => (v === "" ? undefined : Number(v)),
                    })}
                    value={lat ?? ""}
                    onChange={(e) =>
                      setValue(
                        "latitude",
                        e.target.value === "" ? undefined : Number(e.target.value),
                        { shouldDirty: true, shouldValidate: true },
                      )
                    }
                  />
                  <Input
                    placeholder="Longitude"
                    type="number"
                    step="any"
                    width="xs"
                    {...register("longitude", {
                      setValueAs: (v) => (v === "" ? undefined : Number(v)),
                    })}
                    value={lng ?? ""}
                    onChange={(e) =>
                      setValue(
                        "longitude",
                        e.target.value === "" ? undefined : Number(e.target.value),
                        { shouldDirty: true, shouldValidate: true },
                      )
                    }
                  />
                </Flex>
                <Text mt={2} fontSize="xs" color="gray.500">
                  Click on the map to drop a pin and set coordinates.
                </Text>
              </Box>
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

export default AddGreenhouse;
