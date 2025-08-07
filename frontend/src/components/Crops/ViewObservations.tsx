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
  Image,
} from "@chakra-ui/react";
import { useState } from "react";
import { FiEye, FiCamera, FiCalendar, FiBarChart, FiHeart } from "react-icons/fi";
import { format } from "date-fns";

import { 
  CropsService,
  type ZonePublic,
  type ZoneCropObservationPublic,
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

interface ViewObservationsProps {
  zone: ZonePublic;
  zoneCropId?: string; // Optional: for viewing specific historical crop observations
  cropName?: string;   // Optional: for displaying crop name in title
}

const ViewObservations = ({ zone, zoneCropId, cropName }: ViewObservationsProps) => {
  const [isOpen, setIsOpen] = useState(false);

  // If zoneCropId is provided, fetch observations for that specific crop
  // Otherwise, fetch observations for the current active crop in the zone
  const { data: observations, isLoading } = useQuery<ZoneCropObservationPublic[]>({
    queryKey: ["crop-observations", zone.id, zoneCropId],
    queryFn: async (): Promise<ZoneCropObservationPublic[]> => {
      if (zoneCropId) {
        // Fetch observations for specific historical crop
        const token = localStorage.getItem('access_token');
        
        if (!token) {
          throw new Error('No authentication token found');
        }

        const response = await fetch(`/api/v1/crops/zone-crops/${zoneCropId}/observations/`, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
        
        if (!response.ok) {
          if (response.status === 401) {
            throw new Error('Authentication failed - please log in again');
          }
          if (response.status === 404) {
            throw new Error('Zone crop not found');
          }
          throw new Error(`Failed to fetch observations: ${response.status}`);
        }
        return response.json();
      } else {
        // Default behavior - fetch for current active crop
        return CropsService.listZoneCropObservations({ zoneId: zone.id });
      }
    },
    enabled: isOpen,
  });

  const formatDate = (dateString: string) => {
    return format(new Date(dateString), "MMM dd, yyyy 'at' h:mm a");
  };

  const getHealthScoreColor = (score: number) => {
    if (score >= 8) return "green";
    if (score >= 6) return "yellow";
    if (score >= 4) return "orange";
    return "red";
  };

  const getDialogTitle = () => {
    if (cropName && zoneCropId) {
      return `${cropName} Observations - Zone ${zone.zone_number}`;
    }
    return `Crop Observations - Zone ${zone.zone_number}`;
  };

  const getButtonText = () => {
    if (zoneCropId) {
      return "Observations";
    }
    return "View Observations";
  };

  const getButtonSize = () => {
    if (zoneCropId) {
      return "xs"; // Smaller button for historical crops
    }
    return "sm"; // Normal size for current crop
  };

  return (
    <DialogRoot
      size={{ base: "md", md: "xl" }}
      placement="center"
      open={isOpen}
      onOpenChange={({ open }) => setIsOpen(open)}
    >
      <DialogTrigger asChild>
        <Button 
          size={getButtonSize()} 
          colorPalette="blue"
          variant={"solid"}
          onClick={(e) => e.stopPropagation()} // Prevent parent click events
        >
          <FiEye fontSize="12px" />
          {getButtonText()}
        </Button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>{getDialogTitle()}</DialogTitle>
        </DialogHeader>
        
        <DialogBody>
          {isLoading ? (
            <Flex justify="center" align="center" h="200px">
              <Text>Loading observations...</Text>
            </Flex>
          ) : !observations || observations.length === 0 ? (
            <Flex justify="center" align="center" h="200px">
              <VStack gap={2}>
                <Text color="gray.500" fontSize="lg">No observations found</Text>
                <Text color="gray.400" fontSize="sm">
                  {zoneCropId 
                    ? "No observations were recorded for this crop." 
                    : "No observations have been recorded for this crop yet."
                  }
                </Text>
              </VStack>
            </Flex>
          ) : (
            <VStack gap={6} align="stretch" maxH="600px" overflowY="auto">
              {/* Summary Stats */}
              <Box>
                <Heading size="sm" mb={3}>Overview</Heading>
                <HStack gap={6} wrap="wrap">
                  <Box textAlign="center">
                    <Text fontSize="2xl" fontWeight="bold" color="blue.500">{observations.length}</Text>
                    <Text fontSize="sm" color="gray.600">Total Observations</Text>
                  </Box>
                  <Box textAlign="center">
                    <Text fontSize="2xl" fontWeight="bold" color="green.500">
                      {observations?.filter((obs: ZoneCropObservationPublic) => obs.image_url).length || 0}
                    </Text>
                    <Text fontSize="sm" color="gray.600">With Photos</Text>
                  </Box>
                  <Box textAlign="center">
                    <Text fontSize="2xl" fontWeight="bold" color="purple.500">
                      {observations?.filter((obs: ZoneCropObservationPublic) => obs.health_score).length > 0 
                        ? Math.round(
                            observations
                              .filter((obs: ZoneCropObservationPublic) => obs.health_score)
                              .reduce((sum: number, obs: ZoneCropObservationPublic) => sum + (obs.health_score || 0), 0) /
                            observations.filter((obs: ZoneCropObservationPublic) => obs.health_score).length
                          )
                        : "N/A"
                      }
                    </Text>
                    <Text fontSize="sm" color="gray.600">Avg Health Score</Text>
                  </Box>
                </HStack>
              </Box>

              <Separator />

              {/* Observations List */}
              <Box>
                <Heading size="md" mb={4} color="grey.600">
                  <Flex align="center" gap={2}>
                    <FiCalendar />
                    {zoneCropId ? "Historical Observations" : "Recent Observations"}
                  </Flex>
                </Heading>
                <VStack gap={4} align="stretch">
                  {observations
                    ?.filter((obs: ZoneCropObservationPublic) => obs.observed_at)
                    .sort((a: ZoneCropObservationPublic, b: ZoneCropObservationPublic) => 
                      new Date(b.observed_at!).getTime() - new Date(a.observed_at!).getTime()
                    )
                    .map((observation: ZoneCropObservationPublic) => (
                    <Box 
                      key={observation.id} 
                      border="1px" 
                      borderColor="gray.200" 
                      rounded="lg" 
                      p={4}
                      bg="white"
                      _dark={{ bg: "gray.800", borderColor: "gray.600" }}
                      shadow="sm"
                    >
                      {/* Header with date and image indicator */}
                      <Flex justify="space-between" align="start" mb={3}>
                        <VStack align="start" gap={1}>
                          <Text fontSize="sm" fontWeight="bold" color="blue.400">
                            {observation.observed_at ? formatDate(observation.observed_at) : "Date unknown"}
                          </Text>
                          <HStack gap={2}>
                            {observation.health_score && (
                              <Badge 
                                colorPalette={getHealthScoreColor(observation.health_score)} 
                                variant="solid" 
                                size="sm"
                              >
                                <FiHeart fontSize="10px" />
                                Health: {observation.health_score}/10
                              </Badge>
                            )}
                          </HStack>
                        </VStack>
                        
                        {observation.height_cm && (
                          <VStack align="end" gap={1}>
                            <Flex align="center" gap={1} color="gray.600">
                              <FiBarChart fontSize="12px" />
                              <Text fontSize="sm" fontWeight="medium">
                                {observation.height_cm} cm
                              </Text>
                            </Flex>
                          </VStack>
                        )}
                      </Flex>

                      {/* Notes */}
                      {observation.notes && (
                        <Box mb={3}>
                          <Text fontSize="sm" color="gray.700" _dark={{ color: "gray.300" }}>
                            {observation.notes}
                          </Text>
                        </Box>
                      )}

                      {/* Image - Display the actual image if available */}
                      {observation.image_url && (
                        <Box mb={3}>
                          <Text fontSize="sm" fontWeight="medium" mb={2} color="gray.700" _dark={{ color: "gray.300" }}>
                            <Flex align="center" gap={1}>
                              <FiCamera fontSize="12px" />
                              Photo
                            </Flex>
                          </Text>
                          <Image
                            src={observation.image_url}
                            alt="Crop observation"
                            maxW="100%"
                            maxH="300px"
                            objectFit="cover"
                            rounded="md"
                            border="1px"
                            borderColor="gray.200"
                            _dark={{ borderColor: "gray.600" }}
                            cursor="pointer"
                            _hover={{ opacity: 0.8 }}
                            onClick={() => observation.image_url && window.open(observation.image_url, '_blank')}
                          />
                        </Box>
                      )}

                      {/* Metrics Summary */}
                      <Box mt={3} p={3} bg="gray.50" rounded="md" _dark={{ bg: "gray.700" }}>
                        <HStack gap={4} wrap="wrap" fontSize="sm">
                          {observation.height_cm && (
                            <Flex align="center" gap={1}>
                              <FiBarChart color="#6B7280" />
                              <Text>Height: {observation.height_cm} cm</Text>
                            </Flex>
                          )}
                          {observation.health_score && (
                            <Flex align="center" gap={1}>
                              <FiHeart color="#6B7280" />
                              <Text>Health: {observation.health_score}/10</Text>
                            </Flex>
                          )}
                          {!observation.height_cm && !observation.health_score && (
                            <Text color="gray.500" fontSize="xs">No metrics recorded</Text>
                          )}
                        </HStack>
                      </Box>
                    </Box>
                  ))}
                </VStack>
              </Box>

              {/* Growth Trend Summary */}
              {observations && observations.filter((obs: ZoneCropObservationPublic) => obs.height_cm).length > 1 && (
                <>
                  <Separator />
                  <Box>
                    <Heading size="sm" mb={3} color="green.600">
                      Growth Trend
                    </Heading>
                    <Box p={3} bg="green.50" rounded="md" _dark={{ bg: "green.900" }}>
                      {(() => {
                        const heightObservations = observations
                          .filter((obs: ZoneCropObservationPublic) => obs.height_cm && obs.observed_at)
                          .sort((a: ZoneCropObservationPublic, b: ZoneCropObservationPublic) => 
                            new Date(a.observed_at!).getTime() - new Date(b.observed_at!).getTime()
                          );
                        
                        const firstHeight = heightObservations[0]?.height_cm || 0;
                        const lastHeight = heightObservations[heightObservations.length - 1]?.height_cm || 0;
                        const growth = lastHeight - firstHeight;
                        
                        return (
                          <VStack align="start" gap={2}>
                            <Text fontSize="sm" fontWeight="medium">
                              Total Growth: {growth.toFixed(1)} cm
                            </Text>
                            <Text fontSize="xs" color="gray.600" _dark={{ color: "gray.300" }}>
                              From {firstHeight} cm to {lastHeight} cm over {heightObservations.length} measurements
                            </Text>
                          </VStack>
                        );
                      })()}
                    </Box>
                  </Box>
                </>
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

export default ViewObservations;
