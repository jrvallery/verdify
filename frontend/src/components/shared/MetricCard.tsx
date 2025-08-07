import { Box, Flex, Text } from "@chakra-ui/react";
import { ReactNode } from "react";

interface MetricCardProps {
  title: string;
  value: string | number;
  unit?: string;
  icon?: ReactNode;
  gradient?: string;
  idealRange?: string;
  size?: "sm" | "md" | "lg";
  textColor?: string;
}

const MetricCard = ({ 
  title, 
  value, 
  unit, 
  icon, 
  gradient = "linear-gradient(135deg, #6B73FF 0%, #9B59B6 100%)", 
  idealRange,
  size = "md",
  textColor = "white"
}: MetricCardProps) => {
  const sizeStyles = {
    sm: {
      p: 3,
      titleSize: "xs" as const,
      valueSize: "lg" as const,
      iconSize: 16
    },
    md: {
      p: 4,
      titleSize: "sm" as const,
      valueSize: "2xl" as const,
      iconSize: 18
    },
    lg: {
      p: 5,
      titleSize: "md" as const,
      valueSize: "3xl" as const,
      iconSize: 20
    }
  };

  const styles = sizeStyles[size];

  return (
    <Box
      bg={gradient}
      rounded="lg"
      p={styles.p}
      color={textColor}
      position="relative"
    >
      <Flex align="center" gap={2} mb={1}>
        {icon}
        <Text fontSize={styles.titleSize} fontWeight="medium">
          {title}
        </Text>
      </Flex>
      <Text fontSize={styles.valueSize} fontWeight="bold">
        {value}{unit}
      </Text>
      {idealRange && (
        <Text fontSize="xs" mt={1} opacity={0.9}>
          Ideal: {idealRange}
        </Text>
      )}
    </Box>
  );
};

export default MetricCard;
