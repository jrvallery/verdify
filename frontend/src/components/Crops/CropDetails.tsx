import {
  Button,
  DialogActionTrigger,
  DialogTitle,
  Text,
  VStack,
  Box,
  Flex,
  Badge,
  Separator,
} from "@chakra-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FiEye, FiHeart } from "react-icons/fi";

import { 
  CropsService, 
  type ZonePublic,
  type ZoneCropPublic,
  type CropPublic,
  type ZoneCropObservationPublic
} from "@/client";
import useCustomToast from "@/hooks/useCustomToast";
import {
  DialogBody,
  DialogCloseTrigger,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogRoot,
  DialogTrigger,
} from "../ui/dialog";
import AddObservation from "./AddObservation";

interface CropDetailsProps {
  zone: ZonePublic;
  zoneCrop: ZoneCropPublic;
  crop: CropPublic;
}

const CropDetails = ({ zone, zoneCrop, crop }: CropDetailsProps) => {
  const [isOpen, setIsOpen] = useState(false);
  const queryClient = useQueryClient();
  const { showSuccessToast, showErrorToast } = useCustomToast();

  // Get observations for this crop (only fetch if we have a valid zone crop)
  const { data: observations } = useQuery({
    queryKey: ["crop-observations", zone.id],
    queryFn: () => CropsService.listZoneCropObservations({ zoneId: zone.id }),
    enabled: isOpen && !!zoneCrop.id,
    throwOnError: false,
  });

  const harvestMutation = useMutation({
    mutationFn: () => CropsService.harvestCropFromZone({ zoneId: zone.id }),
    onSuccess: () => {
      showSuccessToast("Crop harvested successfully.");
      setIsOpen(false);
      
      // Force remove the zone crop data from cache to prevent 404s
      queryClient.removeQueries({ queryKey: ["zone-crop", zone.id] });
      queryClient.removeQueries({ queryKey: ["crop-observations", zone.id] });
      queryClient.removeQueries({ queryKey: ["zone-has-crop", zone.id] }); // Also remove hasCrop cache
      
      // Invalidate related queries to refetch fresh data
      queryClient.invalidateQueries({ queryKey: ["zones"] });
    },
    onError: () => {
      showErrorToast("Error harvesting crop.");
    },
  });

  const getDaysGrowing = () => {
    if (!zoneCrop.start_date) return 0;

    const startDate = new Date(zoneCrop.start_date);
    const endDate = zoneCrop.end_date ? new Date(zoneCrop.end_date) : new Date();
    const diffTime = Math.abs(endDate.getTime() - startDate.getTime());
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays;
  };

  return (
    <DialogRoot
      size={{ base: "md", md: "lg" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button size="sm" variant="ghost">
          <FiEye fontSize="12px" />
          View Crop
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {crop.name} - Zone {zone.zone_number}
          </DialogTitle>
        </DialogHeader>
        
        <DialogBody>
          <VStack gap={6} align="stretch">
            {/* Crop Info */}
            <Box>
              <Text fontWeight="bold" mb={2}>Crop Information</Text>
              <VStack gap={2} align="stretch">
                <Flex justify="space-between">
                  <Text color={{ base: "gray.600", _dark: "gray.400" }}>Status:</Text>
                  <Badge colorPalette={zoneCrop.is_active ? "green" : "gray"}>
                    {zoneCrop.is_active ? "Active" : "Harvested"}
                  </Badge>
                </Flex>
                <Flex justify="space-between">
                  <Text color={{ base: "gray.600", _dark: "gray.400" }}>Days Growing:</Text>
                  <Text color={{ base: "gray.800", _dark: "gray.200" }}>{getDaysGrowing()} days</Text>
                </Flex>
                <Flex justify="space-between">
                  <Text color={{ base: "gray.600", _dark: "gray.400" }}>Area:</Text>
                  <Text color={{ base: "gray.800", _dark: "gray.200" }}>{zoneCrop.area_sqm ? `${zoneCrop.area_sqm} sq m` : "Not specified"}</Text>
                </Flex>
                {zoneCrop.final_yield && (
                  <Flex justify="space-between">
                    <Text color={{ base: "gray.600", _dark: "gray.400" }}>Final Yield:</Text>
                    <Text color={{ base: "gray.800", _dark: "gray.200" }}>{zoneCrop.final_yield} kg</Text>
                  </Flex>
                )}
                {crop.description && (
                  <Box>
                    <Text color={{ base: "gray.600", _dark: "gray.400" }} fontWeight="medium">Description:</Text>
                    <Text fontSize="sm" color={{ base: "gray.800", _dark: "gray.200" }}>{crop.description}</Text>
                  </Box>
                )}
              </VStack>
            </Box>

            <Separator />

            {/* Observations */}
            <Box>
              <Flex justify="space-between" align="center" mb={4}>
                <Text fontWeight="bold" color={{ base: "gray.800", _dark: "gray.200" }}>Observations ({observations?.length || 0})</Text>
                {zoneCrop.is_active && (
                  <AddObservation zone={zone} />
                )}
              </Flex>
              
              {observations && observations.length > 0 ? (
                <VStack gap={3} align="stretch" maxH="200px" overflowY="auto">
                  {observations.map((obs: ZoneCropObservationPublic) => (
                    <Box 
                      key={obs.id} 
                      p={3} 
                      border="1px" 
                      borderColor={{ base: "gray.200", _dark: "gray.600" }}
                      rounded="md"
                      bg={{ base: "gray.50", _dark: "gray.700" }}
                    >
                      <Flex justify="space-between" align="center" mb={1}>
                        <Text fontSize="sm" fontWeight="medium" color={{ base: "gray.800", _dark: "gray.200" }}>
                          {obs.observed_at ? new Date(obs.observed_at).toLocaleDateString() : "Date unknown"}
                        </Text>
                        {obs.health_score && (
                          <Flex align="center" gap={1}>
                            <FiHeart size={12} />
                            <Text fontSize="sm" color={{ base: "gray.800", _dark: "gray.200" }}>{obs.health_score}/10</Text>
                          </Flex>
                        )}
                      </Flex>
                      {obs.height_cm && (
                        <Text fontSize="sm" color={{ base: "gray.600", _dark: "gray.400" }}>
                          Height: {obs.height_cm} cm
                        </Text>
                      )}
                      {obs.notes && (
                        <Text fontSize="sm" mt={1} color={{ base: "gray.800", _dark: "gray.200" }}>{obs.notes}</Text>
                      )}
                    </Box>
                  ))}
                </VStack>
              ) : (
                <Text color={{ base: "gray.500", _dark: "gray.400" }} fontSize="sm">No observations recorded yet</Text>
              )}
            </Box>
          </VStack>
        </DialogBody>

        <DialogFooter gap={2}>
          {zoneCrop.is_active && (
            <Button
              colorPalette="orange"
              onClick={() => harvestMutation.mutate()}
              loading={harvestMutation.isPending}
            >
              Harvest Crop
            </Button>
          )}
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

export default CropDetails;
