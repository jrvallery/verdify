import { Box, Text, VStack, Badge, Flex } from "@chakra-ui/react";
import { CropPublic, ZoneCropPublic } from "@/client";
import { isCropRecipe } from "@/types/cropRecipe";

interface CropHeaderProps {
  crop: CropPublic;
  zoneCrop: ZoneCropPublic;
  currentStage?: { name: string } | null;
}

const CropHeader = ({ crop, zoneCrop, currentStage }: CropHeaderProps) => {
  const recipe = crop.recipe && isCropRecipe(crop.recipe) ? crop.recipe : null;

  return (
    <Flex justify="space-between" align="center" mb={2}>
      <Box>
        <Text fontSize="2xl" fontWeight="bold" color={{ base: "gray.800", _dark: "gray.100" }}>
          {crop.name}
        </Text>
        <Text fontSize="sm" color={{ base: "gray.600", _dark: "gray.400" }}>
          {recipe?.species || 'Species unknown'}
        </Text>
        <Text fontSize="sm" color={{ base: "gray.600", _dark: "gray.400" }}>
          Planted: {zoneCrop.start_date ? new Date(zoneCrop.start_date).toLocaleDateString() : "Unknown"}
        </Text>
      </Box>
      <VStack gap={1} align="end">
        <Badge 
          colorPalette={zoneCrop.is_active ? "green" : "gray"} 
          size="lg"
          variant="solid"
        >
          {zoneCrop.is_active ? "Growing" : "Harvested"}
        </Badge>
        {currentStage && (
          <Badge colorPalette="blue" size="sm">
            {currentStage.name}
          </Badge>
        )}
      </VStack>
    </Flex>
  );
};

export default CropHeader;
