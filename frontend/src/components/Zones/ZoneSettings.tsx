import {
  Button,
  DialogActionTrigger,
  DialogTitle,
  Text,
  VStack,
  Box,
  Flex,
  Badge,
} from "@chakra-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { FiSettings, FiTrash2, FiPlus, FiMinus } from "react-icons/fi";

import {
  ZonePublic,
  SensorType,
  ZonesService,
  GreenhousesService,
  CropsService
} from "@/client";
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogRoot,
  DialogTrigger,
} from "../ui/dialog";
import useCustomToast from "@/hooks/useCustomToast";
import ViewPastCrops from "./ViewPastCrops";

interface ZoneSettingsProps {
  zone: ZonePublic;
}

const ZoneSettings = ({ zone }: ZoneSettingsProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast, showErrorToast } = useCustomToast();

  const {
    handleSubmit,
    formState: { isSubmitting },
  } = useForm();

  // Get unmapped sensors for this greenhouse
  const { data: unmappedSensors } = useQuery({
    queryKey: ["unmapped-sensors", zone.greenhouse_id],
    queryFn: () => GreenhousesService.listUnmappedGreenhouseSensors({
      greenhouseId: zone.greenhouse_id
    }),
    enabled: isOpen,
  });

  // Get currently mapped sensors for this zone
  const { data: mappedSensors } = useQuery({
    queryKey: ["zone-sensors", zone.id],
    queryFn: () => ZonesService.listZoneSensors({ greenhouseId: zone.greenhouse_id, zoneId: zone.id } as any),
    enabled: isOpen,
  });

  // Get the zone crop data to check if there's an active crop
  const { data: zoneCrop } = useQuery({
    queryKey: ["zone-crop", zone.id],
    queryFn: () => CropsService.getZoneCrop({ zoneId: zone.id }),
    enabled: isOpen,
    retry: false,
    throwOnError: false,
  });

  const deleteZoneMutation = useMutation({
    mutationFn: (zoneId: string) =>
      ZonesService.deleteZone({ greenhouseId: zone.greenhouse_id, zoneId }),
    onSuccess: () => {
      showSuccessToast("Zone deleted successfully.");
      setIsOpen(false);
    },
    onError: () => {
      showErrorToast("An error occurred while deleting the zone.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["zones"] });
    },
  });

  const harvestMutation = useMutation({
    mutationFn: () => CropsService.harvestCropFromZone({ zoneId: zone.id }),
    onSuccess: () => {
      showSuccessToast("Crop harvested successfully.");
      queryClient.removeQueries({ queryKey: ["zone-crop", zone.id] });
      queryClient.removeQueries({ queryKey: ["crop-observations", zone.id] });
      queryClient.removeQueries({ queryKey: ["zone-has-crop", zone.id] });
      queryClient.invalidateQueries({ queryKey: ["zones"] });
    },
    onError: () => {
      showErrorToast("An error occurred while harvesting the crop.");
    },
  });

  const mapSensorMutation = useMutation({
    mutationFn: ({ sensorId, sensorType }: { sensorId: string; sensorType: SensorType }) =>
      ZonesService.mapSensorToZoneEndpoint({
        greenhouseId: zone.greenhouse_id,
        zoneId: zone.id,
        requestBody: { sensor_id: sensorId, type: sensorType }
      } as any),
    onSuccess: () => {
      showSuccessToast("Sensor mapped successfully.");
    },
    onError: () => {
      showErrorToast("An error occurred while mapping the sensor.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["zone-sensors", zone.id] });
      queryClient.invalidateQueries({ queryKey: ["unmapped-sensors", zone.greenhouse_id] });
      queryClient.invalidateQueries({ queryKey: ["zones"] });
    },
  });

  const unmapSensorMutation = useMutation({
    mutationFn: (sensorType: SensorType) =>
      ZonesService.unmapSensorFromZoneEndpoint({
        greenhouseId: zone.greenhouse_id,
        zoneId: zone.id,
        sensorType
      } as any),
    onSuccess: () => {
      showSuccessToast("Sensor unmapped successfully.");
    },
    onError: () => {
      showErrorToast("An error occurred while unmapping the sensor.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["zone-sensors", zone.id] });
      queryClient.invalidateQueries({ queryKey: ["unmapped-sensors", zone.greenhouse_id] });
      queryClient.invalidateQueries({ queryKey: ["zones"] });
    },
  });

  const onDeleteZone = () => {
    deleteZoneMutation.mutate(zone.id);
  };

  const getSensorTypeColor = (type: string) => {
    const colors = {
      temperature: "red",
      humidity: "blue",
      co2: "green",
      light: "yellow",
      soil_moisture: "brown",
    }
    return colors[type as keyof typeof colors] || "gray"
  };

  const getAvailableSensorsForType = (sensorType: SensorType) => {
    return unmappedSensors?.filter(sensor => sensor.type === sensorType) || [];
  };

  const getMappedSensorForType = (sensorType: SensorType) => {
    return mappedSensors?.find(sensor => sensor.type === sensorType);
  };

  const sensorTypes: SensorType[] = ["temperature", "humidity", "co2", "light", "soil_moisture"];

  return (
    <DialogRoot
      size={{ base: "sm", md: "lg" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <FiSettings fontSize="18px" />
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Zone {zone.zone_number} Settings</DialogTitle>
        </DialogHeader>

        <DialogBody>
          <VStack gap={6} align="stretch">
            {/* Zone Info */}
            <Box>
              <Flex justify="space-between" align="center" mb={4}>
                <Text>Location: {zone.location}</Text>
                <ViewPastCrops zone={zone} />
              </Flex>
            </Box>

            {/* Sensor Mapping */}
            <Box>
              <Text fontWeight="bold" mb={4}>Sensor Mapping</Text>
              <VStack gap={4} align="stretch">
                {sensorTypes.map((sensorType) => {
                  const mappedSensor = getMappedSensorForType(sensorType);
                  const availableSensors = getAvailableSensorsForType(sensorType);

                  return (
                    <Box
                      key={sensorType}
                      border="2px"
                      borderColor={{ base: "gray.200", _dark: "gray.600" }}
                      rounded="xl"
                      p={6}
                      shadow="md"
                      bg={{ base: "white", _dark: "gray.800" }}
                      _hover={{
                        shadow: "lg",
                        borderColor: { base: "gray.300", _dark: "gray.500" }
                      }}
                    >
                      <Flex justify="space-between" align="center" mb={4}>
                        <Box>
                          <Badge colorPalette={getSensorTypeColor(sensorType)} size="lg">
                            {sensorType}
                          </Badge>
                        </Box>
                      </Flex>

                      {mappedSensor ? (
                        <Flex justify="space-between" align="center">
                          <Box>
                            <Text fontWeight="medium" color={{ base: "gray.800", _dark: "gray.200" }}>
                              {mappedSensor.name}
                            </Text>
                            <Text fontSize="sm" color={{ base: "gray.600", _dark: "gray.400" }}>
                              {mappedSensor.model || "No model specified"}
                            </Text>
                          </Box>
                          <Button
                            variant="ghost"
                            colorPalette="red"
                            size="sm"
                            onClick={() => unmapSensorMutation.mutate(sensorType)}
                            loading={unmapSensorMutation.isPending}
                          >
                            <FiMinus />
                          </Button>
                        </Flex>
                      ) : (
                        <Box>
                          <Text fontSize="sm" color={{ base: "gray.500", _dark: "gray.400" }} mb={3}>
                            No sensor mapped
                          </Text>
                          {availableSensors.length > 0 ? (
                            <VStack gap={3} align="stretch">
                              {availableSensors.map((sensor) => (
                                <Box
                                  key={sensor.id}
                                  border="1px"
                                  borderColor={{ base: "gray.300", _dark: "gray.600" }}
                                  rounded="lg"
                                  p={3}
                                  bg={{ base: "gray.50", _dark: "gray.700" }}
                                >
                                  <Flex justify="space-between" align="center">
                                    <Box>
                                      <Text fontSize="sm" fontWeight="medium" color={{ base: "gray.800", _dark: "gray.200" }}>
                                        {sensor.name}
                                      </Text>
                                      <Text fontSize="xs" color={{ base: "gray.600", _dark: "gray.400" }}>
                                        {sensor.model || "No model"}
                                      </Text>
                                    </Box>
                                    <Button
                                      variant="ghost"
                                      colorPalette="green"
                                      size="sm"
                                      onClick={() => mapSensorMutation.mutate({
                                        sensorId: sensor.id,
                                        sensorType
                                      })}
                                      loading={mapSensorMutation.isPending}
                                    >
                                      <FiPlus />
                                    </Button>
                                  </Flex>
                                </Box>
                              ))}
                            </VStack>
                          ) : (
                            <Text fontSize="sm" color={{ base: "gray.400", _dark: "gray.500" }}>
                              No available {sensorType} sensors
                            </Text>
                          )}
                        </Box>
                      )}
                    </Box>
                  );
                })}
              </VStack>
            </Box>

            {/* Delete Zone */}
            <Box pt={4} borderTop="1px" borderColor="gray.200">
              <Text fontWeight="bold" color="red.500" mb={4}>Danger Zone</Text>

              {/* Harvest Crop Button - only show if there's an active crop */}
              {zoneCrop?.is_active && (
                <Box mb={4}>
                  <Text fontSize="sm" color="gray.600" mb={2}>
                    Harvest the current crop to remove it from this zone (preserves historical data)
                  </Text>
                  <Button
                    variant="solid"
                    colorPalette="orange"
                    size="sm"
                    onClick={() => harvestMutation.mutate()}
                    loading={harvestMutation.isPending}
                  >
                    <FiTrash2 />
                    Harvest Crop
                  </Button>
                </Box>
              )}

              {/* Delete Zone Button */}
              <Box>
                <Text fontSize="sm" color="gray.600" mb={2}>
                  Permanently delete this zone and all its data
                </Text>
                <form onSubmit={handleSubmit(onDeleteZone)}>
                  <Button
                    variant="solid"
                    colorPalette="red"
                    size="sm"
                    type="submit"
                    loading={isSubmitting}
                  >
                    <FiTrash2 />
                    Delete Zone
                  </Button>
                </form>
              </Box>
            </Box>
          </VStack>
        </DialogBody>

        <DialogFooter>
          <DialogActionTrigger asChild>
            <Button variant="subtle" colorPalette="gray">
              Close
            </Button>
          </DialogActionTrigger>
        </DialogFooter>

        <DialogCloseTrigger />
      </DialogContent>
    </DialogRoot>
  );
};

export default ZoneSettings;
