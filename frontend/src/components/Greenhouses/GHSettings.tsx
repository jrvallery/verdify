import { useEffect, useState } from "react";
import { Box, Button, Flex, Heading, Input, Text, VStack } from "@chakra-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "@tanstack/react-router";
import { GreenhousesService, type GreenhousePublic } from "@/client";
import type { ApiError } from "@/client/core/ApiError";
import useCustomToast from "@/hooks/useCustomToast";
import { handleError } from "@/utils";
import { LocationMap } from "@/components/Common/LocationMap";

const GHSettings = () => {
  const { greenhouseId } = useParams({ from: "/greenhouses/$greenhouseId/settings" });
  const router = useRouter();
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  const { data: greenhouse, isLoading } = useQuery({
    queryKey: ["greenhouse", greenhouseId],
    queryFn: () => GreenhousesService.readGreenhouse({ greenhouseId }),
    enabled: !!greenhouseId,
  });

  const [title, setTitle] = useState<string>("");
  const [latitude, setLatitude] = useState<number | undefined>(undefined);
  const [longitude, setLongitude] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (greenhouse) {
      setTitle(greenhouse.title ?? "");
      setLatitude(greenhouse.latitude ?? undefined);
      setLongitude(greenhouse.longitude ?? undefined);
    }
  }, [greenhouse]);

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<GreenhousePublic>) =>
      GreenhousesService.updateGreenhouse({
        greenhouseId,
        requestBody: {
          title: payload.title,
          latitude: payload.latitude,
          longitude: payload.longitude,
        } as any,
      }),
    onSuccess: () => {
      showSuccessToast("Greenhouse updated.");
      queryClient.invalidateQueries({ queryKey: ["greenhouse", greenhouseId] });
    },
    onError: (err: ApiError) => handleError(err),
  });

  const deleteMutation = useMutation({
    mutationFn: () => GreenhousesService.deleteGreenhouse({ greenhouseId }),
    onSuccess: () => {
      showSuccessToast("Greenhouse deleted.");
      queryClient.invalidateQueries({ queryKey: ["greenhouses"] });
      router.navigate({ to: "/" });
    },
    onError: (err: ApiError) => handleError(err),
  });

  const onSave = () => {
    updateMutation.mutate({
      title: title?.trim() || greenhouse?.title,
      latitude,
      longitude,
    } as Partial<GreenhousePublic>);
  };

  const onDelete = () => {
    deleteMutation.mutate();
  };

  return (
    <Box p={6}>
      <Heading size="lg" mb={6}>
        Greenhouse Settings
      </Heading>

      <VStack align="stretch" gap={4} maxW="640px">
        <Box>
          <Text mb={1} fontWeight="medium">
            Name
          </Text>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Greenhouse name"
            disabled={isLoading || updateMutation.isPending}
          />
        </Box>

        <Box>
          <Text mb={2} fontWeight="medium">
            Location
          </Text>
          <LocationMap
            lat={latitude}
            lng={longitude}
            onChange={(newLat, newLng) => {
              setLatitude(newLat);
              setLongitude(newLng);
            }}
            height={360}
          />
          <Flex gap={3} mt={3} wrap="wrap">
            <Input
              placeholder="Latitude"
              value={latitude ?? ""}
              onChange={(e) => {
                const v = e.target.value === "" ? undefined : Number(e.target.value)
                setLatitude(Number.isFinite(v as any) ? (v as number | undefined) : undefined)
              }}
              type="number"
              step="any"
              width="xs"
            />
            <Input
              placeholder="Longitude"
              value={longitude ?? ""}
              onChange={(e) => {
                const v = e.target.value === "" ? undefined : Number(e.target.value)
                setLongitude(Number.isFinite(v as any) ? (v as number | undefined) : undefined)
              }}
              type="number"
              step="any"
              width="xs"
            />
          </Flex>
          <Text mt={2} fontSize="xs" color="gray.500">
            Click on the map to drop a pin and set coordinates.
          </Text>
        </Box>

        <Flex gap={3}>
          <Button
            variant="solid"
            colorPalette="blue"
            onClick={onSave}
            loading={updateMutation.isPending}
          >
            Save Changes
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              // Reset fields to current server values
              setTitle(greenhouse?.title ?? "");
              setLatitude(greenhouse?.latitude ?? undefined);
              setLongitude(greenhouse?.longitude ?? undefined);
            }}
            disabled={isLoading || updateMutation.isPending}
          >
            Reset
          </Button>
        </Flex>

        <Box mt={8} borderTop="1px" borderColor="gray.200" pt={4}>
          <Heading size="sm" color="red.600" mb={2}>
            Danger Zone
          </Heading>
          <Text fontSize="sm" color="gray.600" mb={3}>
            Deleting a greenhouse cannot be undone.
          </Text>
          <form onSubmit={(e) => { e.preventDefault(); onDelete(); }}>
            <Button
              variant="solid"
              colorPalette="red"
              type="submit"
              loading={deleteMutation.isPending}
            >
              Delete Greenhouse
            </Button>
          </form>
        </Box>
      </VStack>
    </Box>
  );
};

export default GHSettings;
