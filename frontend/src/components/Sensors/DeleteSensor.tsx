import { Button, DialogTitle, Text } from "@chakra-ui/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { FiTrash2 } from "react-icons/fi";

import { SensorsService } from "@/client";
import {
  DialogActionTrigger,
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogRoot,
  DialogTrigger,
} from "@/components/ui/dialog";
import useCustomToast from "@/hooks/useCustomToast";

interface DeleteSensorProps {
  id: string;
  controllerId: string;
}

const DeleteSensor = ({ id, controllerId }: DeleteSensorProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast, showErrorToast } = useCustomToast();
  const {
    handleSubmit,
    formState: { isSubmitting },
  } = useForm();

  const deleteSensor = async (id: string) => {
    await SensorsService.deleteSensor({ sensorId: id });
  };

  const mutation = useMutation({
    mutationFn: deleteSensor,
    onSuccess: () => {
      showSuccessToast("The sensor was deleted successfully.");
      setIsOpen(false);
    },
    onError: () => {
      showErrorToast("An error occurred while deleting the sensor.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["sensors", controllerId] });
    },
  });

  const onSubmit = () => {
    mutation.mutate(id);
  };

  return (
    <DialogRoot
      size={{ base: "xs", md: "md" }}
      placement="center"
      role="alertdialog"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="xs" colorPalette="red">
          <FiTrash2 fontSize="12px" />
        </Button>
      </DialogTrigger>

      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogCloseTrigger />
          <DialogHeader>
            <DialogTitle>Delete Sensor</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text mb={4}>
              This sensor will be permanently deleted. If it's mapped to a zone, it will be unmapped first. Are you sure? You will not
              be able to undo this action.
            </Text>
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
              colorPalette="red"
              type="submit"
              loading={isSubmitting}
            >
              Delete
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </DialogRoot>
  );
};

export default DeleteSensor;
