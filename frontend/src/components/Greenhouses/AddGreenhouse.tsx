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

const AddGreenhouse = () => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isValid, isSubmitting },
  } = useForm<GreenhouseCreate>({
    mode: "onBlur",
    criteriaMode: "all",
    defaultValues: {
      title: "",
      description: "",
      type: "",
      longitude: undefined,
      latitude: undefined,
    },
  });

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
    mutation.mutate(data);
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

              <Field
              invalid={!!errors.type}
              errorText={errors.type?.message}
              label="Type"
            >
            <select id="type" {...register("type")}>
              <option value="Quonset">Quonset</option>
              <option value="Standard">Standard</option>
            </select>
          </Field>
              <Field
                required
                errorText={errors.longitude?.message}
                label="Longitude"
              >
                <Input
                  id="longitude"
                  type="number"
                  step="any"
                  {...register("longitude", {
                    required: "Longitude is required.",
                    valueAsNumber: true,
                  })}
                  placeholder="Longitude"
                />
              </Field>
              <Field
                required
                errorText={errors.latitude?.message}
                label="Latitude"
              >
                <Input
                  id="latitude"
                  type="number"
                  step="any"
                  {...register("latitude", {
                    required: "Latitude is required.",
                    valueAsNumber: true,
                  })}
                  placeholder="Latitude"
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

export default AddGreenhouse;
