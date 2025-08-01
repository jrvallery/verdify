import { createFileRoute } from '@tanstack/react-router'
import {
  Box,
  Container,
  Flex,
  Heading,
  Text,
  Badge,
  SimpleGrid,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"

import { ZonesService, ZonePublic, CropsService } from "@/client"
import AddZone from "@/components/Zones/AddZone"
import ZoneSettings from "@/components/Zones/ZoneSettings"
import PlantCrop from "@/components/Crops/PlantCrop"
import CropDetails from "@/components/Crops/CropDetails"

export const Route = createFileRoute('/greenhouses/$greenhouseId/zones')({
  component: Zones
})

function Zones() {
  const { greenhouseId } = Route.useParams()

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
        Zones Management
      </Heading>

      <AddZone greenhouseId={greenhouseId} />

      <SimpleGrid columns={{ base: 1, md: 2, lg: 3 }} gap={6} mt={6}>
        {zones?.map((zone: ZonePublic) => (
          <ZoneCard key={zone.id} zone={zone} />
        ))}
      </SimpleGrid>
    </Container>
  )
}

function ZoneCard({ zone }: { zone: ZonePublic }) {
  // Get current crop for this zone
  const { data: zoneCrop, error: zoneCropError } = useQuery({
    queryKey: ["zone-crop", zone.id],
    queryFn: () => CropsService.getZoneCrop({ zoneId: zone.id }),
    retry: false, // Don't retry if no crop is planted
  });

  // Get crop details if there's an active crop
  const { data: crop } = useQuery({
    queryKey: ["crop", zoneCrop?.crop_id],
    queryFn: () => CropsService.getCrop({ cropId: zoneCrop!.crop_id }),
    enabled: !!zoneCrop?.crop_id,
  });

  // Check if there's no crop (either error or no data)
  const hasNoCrop = !!zoneCropError || !zoneCrop;

  return (
    <Box
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
      position="relative"
    >
      {/* Settings Button */}
      <Box position="absolute" top={4} right={4}>
        <ZoneSettings zone={zone} />
      </Box>

      {/* Zone Header */}
      <Box mb={4} pr={10}>
        <Heading size="lg" color={{ base: "gray.800", _dark: "gray.100" }}>
          Zone {zone.zone_number}
        </Heading>
        <Badge colorPalette="orange" size="md">
          {zone.location}
        </Badge>
      </Box>

      {/* Zone Data */}
      <Box mb={4}>
        <Flex justify="space-between" mb={2}>
          <Text color={{ base: "gray.600", _dark: "gray.400" }}>Temperature:</Text>
          <Text color={{ base: "gray.800", _dark: "gray.200" }}>
            {zone.temperature ? `${zone.temperature}°C` : "Null"}
          </Text>
        </Flex>
        <Flex justify="space-between" mb={4}>
          <Text color={{ base: "gray.600", _dark: "gray.400" }}>Humidity:</Text>
          <Text color={{ base: "gray.800", _dark: "gray.200" }}>
            {zone.humidity ? `${zone.humidity}%` : "Null"}
          </Text>
        </Flex>
      </Box>

      {/* Crop Section */}
      <Box 
        border="1px" 
        borderColor={{ base: "gray.300", _dark: "gray.600" }}
        rounded="lg" 
        p={4}
        bg={{ base: "gray.50", _dark: "gray.700" }}
      >
        <Text fontWeight="bold" mb={3} color={{ base: "gray.800", _dark: "gray.200" }}>
          Current Crop
        </Text>
        
        {zoneCrop && crop && !hasNoCrop ? (
          <Box>
            <Flex justify="space-between" align="center" mb={2}>
              <Text fontWeight="medium" color={{ base: "gray.800", _dark: "gray.200" }}>
                {crop.name}
              </Text>
              <Badge colorPalette={zoneCrop.is_active ? "green" : "gray"} size="sm">
                {zoneCrop.is_active ? "Active" : "Harvested"}
              </Badge>
            </Flex>
            <Text fontSize="sm" color={{ base: "gray.600", _dark: "gray.400" }} mb={3}>
              Planted: {zoneCrop.start_date ? new Date(zoneCrop.start_date).toLocaleDateString() : "Date unknown"}
            </Text>
            <CropDetails zone={zone} zoneCrop={zoneCrop} crop={crop} />
          </Box>
        ) : (
          <Box textAlign="center">
            <Text color={{ base: "gray.500", _dark: "gray.400" }} mb={3} fontSize="sm">
              No crop currently planted
            </Text>
            <PlantCrop zone={zone} />
          </Box>
        )}
      </Box>
    </Box>
  )
}