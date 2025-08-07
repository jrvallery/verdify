import { useQuery } from "@tanstack/react-query";
import {
  Button,
  DialogTitle,
  Text,
  VStack,
  Box,
  Flex,
  Badge,
  HStack,
  Heading,
  Separator,
} from "@chakra-ui/react";
import { useState } from "react";
import { FiCalendar, FiClock, FiTrendingUp, FiEye } from "react-icons/fi";
import { format, differenceInDays } from "date-fns";

import { 
  CropsService,
  type ZonePublic,
  type ZoneCropPublic 
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
import ViewObservations from "../Crops/ViewObservations";

interface ViewPastCropsProps {
  zone: ZonePublic;
}

const ViewPastCrops = ({ zone }: ViewPastCropsProps) => {
  const [isOpen, setIsOpen] = useState(false);

  const { data: pastCrops, isLoading } = useQuery({
    queryKey: ["zone-crop-history", zone.id],
    queryFn: () => CropsService.listZoneCropHistory({ zoneId: zone.id }),
    enabled: isOpen,
  });

  // Fetch crop details for each zone crop to get the crop names
  const { data: cropDetails } = useQuery({
    queryKey: ["crop-details", pastCrops?.map(c => c.crop_id)],
    queryFn: async () => {
      if (!pastCrops?.length) return {};
      
      const cropDetailsMap: Record<string, any> = {};
      
      // Fetch crop details for each unique crop_id
      const uniqueCropIds = [...new Set(pastCrops.map(c => c.crop_id))];
      
      await Promise.all(
        uniqueCropIds.map(async (cropId) => {
          try {
            const cropDetail = await CropsService.getCrop({ cropId });
            cropDetailsMap[cropId] = cropDetail;
          } catch (error) {
            console.error(`Failed to fetch crop ${cropId}:`, error);
            cropDetailsMap[cropId] = { name: "Unknown Crop" };
          }
        })
      );
      
      return cropDetailsMap;
    },
    enabled: isOpen && !!pastCrops?.length,
  });

  const getCropName = (zoneCrop: ZoneCropPublic) => {
    return cropDetails?.[zoneCrop.crop_id]?.name || "Loading...";
  };

  const getCropStatusBadge = (crop: ZoneCropPublic) => {
    if (crop.is_active) {
      return <Badge colorPalette="green" variant="solid" size="sm">Active</Badge>;
    }
    return <Badge colorPalette="gray" variant="outline" size="sm">Completed</Badge>;
  };

  const formatDate = (dateString: string) => {
    return format(new Date(dateString), "MMM dd, yyyy");
  };

  const getDurationText = (crop: ZoneCropPublic) => {
    if (!crop.start_date) return "N/A";
    const start = new Date(crop.start_date);
    const end = crop.end_date ? new Date(crop.end_date) : new Date();
    const days = differenceInDays(end, start);
    return `${days} days`;
  };

  const activeCrops = pastCrops?.filter(crop => crop.is_active) || [];
  const completedCrops = pastCrops?.filter(crop => !crop.is_active) || [];

  return (
    <DialogRoot
      size={{ base: "md", md: "xl" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" colorPalette="blue">
          <FiEye fontSize="12px" />
          View Past Crops
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Crop History - Zone {zone.zone_number}</DialogTitle>
        </DialogHeader>
        
        <DialogBody>
          {isLoading ? (
            <Flex justify="center" align="center" h="200px">
              <Text>Loading crop history...</Text>
            </Flex>
          ) : !pastCrops || pastCrops.length === 0 ? (
            <Flex justify="center" align="center" h="200px">
              <VStack gap={2}>
                <Text color="gray.500" fontSize="lg">No crops found</Text>
                <Text color="gray.400" fontSize="sm">This zone has no crop history yet.</Text>
              </VStack>
            </Flex>
          ) : (
            <VStack gap={6} align="stretch" maxH="600px" overflowY="auto">
              {/* Summary Stats */}
              <Box>
                <Heading size="sm" mb={3}>Overview</Heading>
                <HStack gap={6} wrap="wrap">
                  <Box textAlign="center">
                    <Text fontSize="2xl" fontWeight="bold" color="blue.500">{pastCrops.length}</Text>
                    <Text fontSize="sm" color="gray.600">Total Crops</Text>
                  </Box>
                  <Box textAlign="center">
                    <Text fontSize="2xl" fontWeight="bold" color="green.500">{activeCrops.length}</Text>
                    <Text fontSize="sm" color="gray.600">Active</Text>
                  </Box>
                  <Box textAlign="center">
                    <Text fontSize="2xl" fontWeight="bold" color="purple.500">
                        {pastCrops.reduce((total, crop) => {
                            if (!crop.start_date) return total;
                            const start = new Date(crop.start_date);
                            const end = crop.end_date ? new Date(crop.end_date) : new Date();
                            return total + differenceInDays(end, start);
                        }, 0)}
                    </Text>
                    <Text fontSize="sm" color="gray.600">Total Days</Text>
                  </Box>
                </HStack>
              </Box>

              <Separator />

              {/* Active Crops */}
              {activeCrops.length > 0 && (
                <Box>
                  <Heading size="md" mb={4} color="green.600">
                    <Flex align="center" gap={2}>
                      <FiTrendingUp />
                      Active Crops
                    </Flex>
                  </Heading>
                  <VStack gap={3} align="stretch">
                    {activeCrops.map((crop) => (
                      <Box 
                        key={crop.id} 
                        border="2px" 
                        borderColor="green.200" 
                        rounded="lg" 
                        p={4}
                        bg="green.50"
                        _dark={{ bg: "green.900", borderColor: "green.700" }}
                        _hover={{ 
                          shadow: "md",
                          borderColor: "green.300",
                          cursor: "pointer"
                        }}
                        onClick={() => {
                          // Handle click to view observations
                        }}
                      >
                        <Flex justify="space-between" align="start" mb={3}>
                          <VStack align="start" gap={1}>
                            <Text fontWeight="bold">{getCropName(crop)}</Text>
                            {getCropStatusBadge(crop)}
                          </VStack>
                          <VStack align="end" gap={1}>
                            <Text fontSize="sm" color="gray.500">
                              Started {crop.start_date ? formatDate(crop.start_date) : "N/A"}
                            </Text>
                            <ViewObservations 
                              zone={zone} 
                              zoneCropId={crop.id}
                              cropName={getCropName(crop)}
                            />
                          </VStack>
                        </Flex>

                        <HStack gap={4} wrap="wrap" fontSize="sm">
                          <Flex align="center" gap={1}>
                            <FiClock color="#6B7280" />
                            <Text>{getDurationText(crop)} growing</Text>
                          </Flex>
                          {crop.area_sqm && (
                            <Text>Area: {crop.area_sqm} m²</Text>
                          )}
                        </HStack>
                      </Box>
                    ))}
                  </VStack>
                </Box>
              )}

              {/* Completed Crops */}
              {completedCrops.length > 0 && (
                <Box>
                  <Heading size="md" mb={4} color="gray.600">
                    <Flex align="center" gap={2}>
                      <FiCalendar />
                      Completed Crops
                    </Flex>
                  </Heading>
                  <VStack gap={3} align="stretch">
                    {completedCrops
                      .sort((a, b) => new Date(b.end_date!).getTime() - new Date(a.end_date!).getTime())
                      .map((crop) => (
                      <Box 
                        key={crop.id} 
                        border="1px" 
                        borderColor="gray.200" 
                        rounded="lg" 
                        p={4}
                        bg="white"
                        _dark={{ bg: "gray.800", borderColor: "gray.600" }}
                        _hover={{ 
                          shadow: "md",
                          borderColor: "gray.300",
                          cursor: "pointer"
                        }}
                      >
                        <Flex justify="space-between" align="start" mb={3}>
                          <VStack align="start" gap={1}>
                            <Text fontWeight="bold">{getCropName(crop)}</Text>
                            {getCropStatusBadge(crop)}
                          </VStack>
                          <VStack align="end" gap={1}>
                            <Text fontSize="xs" color="gray.500">
                              {crop.start_date ? formatDate(crop.start_date) : "N/A"} - {crop.end_date ? formatDate(crop.end_date) : "Ongoing"}
                            </Text>
                            <Text fontSize="xs" color="gray.400">
                              {getDurationText(crop)}
                            </Text>
                            <ViewObservations 
                              zone={zone} 
                              zoneCropId={crop.id}
                              cropName={getCropName(crop)}
                            />
                          </VStack>
                        </Flex>
                      </Box>
                    ))}
                  </VStack>
                </Box>
              )}
            </VStack>
          )}
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => setIsOpen(false)}>
            Close
          </Button>
        </DialogFooter>
        
        <DialogCloseTrigger />
      </DialogContent>
    </DialogRoot>
  );
};

export default ViewPastCrops;
