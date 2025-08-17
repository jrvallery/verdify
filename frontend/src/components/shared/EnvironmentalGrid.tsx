import { SimpleGrid } from "@chakra-ui/react";
import { FiThermometer, FiDroplet } from "react-icons/fi";
import MetricCard from "./MetricCard";
import { ZonePublic } from "@/client";
import { CropRecipe } from "@/types/cropRecipe";

export interface EnvironmentalGridProps {
  zone: ZonePublic;
  idealConditions?: CropRecipe['ideal_conditions'] | null;
}

const EnvironmentalGrid = ({ zone, idealConditions }: EnvironmentalGridProps) => {
  return (
    <SimpleGrid columns={2} gap={4}>
      <MetricCard
        title="Temperature"
        value={zone.temperature || "--"}
        unit={zone.temperature ? "°C" : ""}
        icon={<FiThermometer size={18} />}
        gradient="linear-gradient(135deg,rgb(195, 21, 21) 0%, #FF8E8E 100%)"
        idealRange={
          idealConditions?.temperature_C
            ? `${idealConditions.temperature_C.min}-${idealConditions.temperature_C.max}°C`
            : undefined
        }
      />

      <MetricCard
        title="Humidity"
        value={zone.humidity || "--"}
        unit={zone.humidity ? "%" : ""}
        icon={<FiDroplet size={18} />}
        gradient="linear-gradient(135deg,rgb(95, 78, 205) 0%, #6EE8E0 100%)"
        idealRange={
          idealConditions?.['humidity_%']
            ? `${idealConditions['humidity_%'].min}-${idealConditions['humidity_%'].max}%`
            : undefined
        }
      />
    </SimpleGrid>
  );
};

export default EnvironmentalGrid;
