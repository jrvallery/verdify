import { createFileRoute } from '@tanstack/react-router'
import {
  Box,
  Container,
  Flex,
  Heading,
  Text,
  Badge,
  SimpleGrid,
  VStack,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"

import { ZonesService, ZonePublic } from "@/client"
import { GreenhousesService } from "@/client"
import AddZone from "@/components/Zones/AddZone"
import ZoneSettings from "@/components/Zones/ZoneSettings"
import PlantCrop from "@/components/Crops/PlantCrop"
import AddObservation from "@/components/Crops/AddObservation"
import ViewObservations from "@/components/Crops/ViewObservations"
import { useCropQueries } from "@/hooks/useCropQueries";
import { useCropStageData } from "@/hooks/useCropStageData";
import EnvironmentalGrid from "@/components/shared/EnvironmentalGrid";
import CropHeader from "@/components/Crops/CropHeader";
import { isCropRecipe } from "@/types/cropRecipe";

export const Route = createFileRoute('/greenhouses/$greenhouseId/zones')({
  component: Zones
})

function Zones() {
  const { greenhouseId } = Route.useParams()

  const { data: greenhouse } = useQuery({
    queryKey: ["greenhouse", greenhouseId],
    queryFn: () => GreenhousesService.readGreenhouse({ greenhouseId }),
  })

  const {
    data: zones,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["zones", greenhouseId],
    queryFn: () => ZonesService.listZones({ greenhouseId }),
  })

  if (isLoading) return <Text>Loading...</Text>
  if (isError) return <Text>Error loading zones</Text>

  return (
    <Container maxW="full">
      <Heading size="lg" textAlign={{ base: "center", md: "left" }} pt={12}>
        {greenhouse?.title ?? "Zones Management"}
      </Heading>
      {greenhouse?.latitude && (
        <Text mt={1} textAlign={{ base: "center", md: "left" }} color="gray.500">
          {greenhouse.longitude}
        </Text>
      )}

      <AddZone greenhouseId={greenhouseId} />

      <SimpleGrid minChildWidth="400px" gap={6} mt={6}>
        {zones?.map((zone: ZonePublic) => (
          <ZoneCard key={zone.id} zone={zone} />
        ))}
      </SimpleGrid>
    </Container>
  )
}

function ZoneCard({ zone }: { zone: ZonePublic }) {
  // Use our custom hook for all crop-related queries
  const { 
    zoneCrop, 
    crop, 
    observations, 
    isLoading, 
    hasNoCrop 
  } = useCropQueries(zone);

  // Use our custom hook for stage calculations
  const {
    currentStage,
    nextStage,
    daysUntilNext,
    progress,
    daysGrowing
  } = useCropStageData(zoneCrop, crop, observations);


  // Safely access recipe data
  const recipe = crop?.recipe && isCropRecipe(crop.recipe) ? crop.recipe : null;
  const idealConditions = recipe?.ideal_conditions || null;

  return (
    <Box
      border="2px"
      borderColor={{ base: "gray.200", _dark: "gray.600" }}
      rounded="xl"
      p={{ base: 4, md: 6 }}
      shadow="lg"
      bg={{ base: "white", _dark: "gray.800" }}
      _hover={{
        shadow: "xl",
        transform: "translateY(-2px)",
        borderColor: { base: "gray.300", _dark: "gray.500" }
      }}
      position="relative"
      minH={{ base: "auto", md: "600px" }}
      h="fit-content"
      transition="all 0.2s ease"
      overflow="hidden"
    >
      <Box position="absolute" top={4} right={4} zIndex={1}>
        <ZoneSettings zone={zone} />
      </Box>

      <Box mb={6} pr={12}>
        <Heading 
          size={{ base: "lg", md: "xl" }} 
          color={{ base: "gray.800", _dark: "gray.100" }} 
          mb={2}
          lineClamp={1}
        >
          Zone {zone.zone_number}
        </Heading>
        <Badge colorPalette="yellow" size={{ base: "md", md: "lg" }} variant="subtle">
          {zone.location}
        </Badge>
      </Box>

      <Box mb={6}>
        <EnvironmentalGrid zone={zone} idealConditions={idealConditions} />
      </Box>

      <Box 
        border="2px" 
        borderColor={{ base: "green.200", _dark: "green.600" }}
        rounded="xl" 
        p={{ base: 3, md: 5 }}
        bg="linear-gradient(135deg, #f0fff4 0%, #e6fffa 100%)"
        _dark={{ bg: "linear-gradient(135deg, #1a2f1a 0%, #1a2e2a 100%)" }}
        minH={{ base: "300px", md: "400px" }}
      >
        {isLoading ? (
          <Flex justify="center" align="center" h="200px">
            <Text 
              color={{ base: "gray.500", _dark: "gray.400" }} 
              fontSize={{ base: "md", md: "lg" }}
              textAlign="center"
            >
              Loading crop data...
            </Text>
          </Flex>
        ) : zoneCrop && crop && !hasNoCrop ? (
          <VStack gap={{ base: 3, md: 5 }} align="stretch" h="full">
            <CropHeader 
              crop={crop} 
              zoneCrop={zoneCrop} 
              currentStage={currentStage}
            />

            {/* Growth Progress */}
            {recipe?.growth_duration_days && zoneCrop.is_active && (
              <Box
                bg={{ base: "white", _dark: "gray.700" }}
                border="1px"
                borderColor={{ base: "green.300", _dark: "green.600" }}
                rounded="lg"
                p={{ base: 3, md: 4 }}
              >
                <Flex justify="space-between" align="center" mb={2} wrap="wrap" gap={2}>
                  <Text 
                    fontSize={{ base: "xs", md: "sm" }} 
                    fontWeight="medium" 
                    color={{ base: "gray.700", _dark: "gray.300" }}
                  >
                    Growth Progress
                  </Text>
                  <Text 
                    fontSize={{ base: "xs", md: "sm" }} 
                    color={{ base: "gray.600", _dark: "gray.400" }}
                  >
                    {progress.toFixed(1)}%
                  </Text>
                </Flex>
                <Box
                  bg={{ base: "gray.200", _dark: "gray.600" }}
                  rounded="full"
                  h="3"
                  mb={2}
                >
                  <Box
                    bg="linear-gradient(90deg, #22C55E 0%, #16A34A 100%)"
                    h="full"
                    rounded="full"
                    w={`${progress}%`}
                    transition="width 0.3s ease"
                  />
                </Box>
                <Flex 
                  justify="space-between" 
                  fontSize="xs" 
                  color={{ base: "gray.500", _dark: "gray.400" }}
                  wrap="wrap"
                  gap={1}
                >
                  <Text>{daysGrowing} days grown</Text>
                  <Text>{recipe.growth_duration_days - daysGrowing} days remaining</Text>
                </Flex>
                {nextStage && daysUntilNext && (
                  <Text 
                    fontSize="xs" 
                    color={{ base: "blue.600", _dark: "blue.400" }} 
                    mt={1}
                    lineClamp={2}
                  >
                    Next stage: {nextStage.name} in {daysUntilNext} days
                  </Text>
                )}
              </Box>
            )}

            {/* Action Buttons */}
            <Box pt={2}>
              <SimpleGrid columns={{ base: 1, sm: 2 }} gap={3}>
                {zoneCrop.is_active && (
                  <>
                    <AddObservation zone={zone} />
                    <ViewObservations zone={zone} />
                  </>
                )}
                {!zoneCrop.is_active && (
                  <Box gridColumn={{ base: "span 1", sm: "span 2" }}>
                    <PlantCrop zone={zone} />
                  </Box>
                )}
              </SimpleGrid>
            </Box>
          </VStack>
        ) : (
          <Flex direction="column" justify="center" align="center" h="200px" gap={4}>
            <Text 
              color={{ base: "gray.500", _dark: "gray.400" }} 
              fontSize={{ base: "md", md: "lg" }} 
              textAlign="center"
              px={2}
            >
              No crop currently planted
            </Text>
            <PlantCrop zone={zone} />
          </Flex>
        )}
      </Box>
    </Box>
  )
}