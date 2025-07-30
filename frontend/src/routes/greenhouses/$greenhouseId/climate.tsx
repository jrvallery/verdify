import { createFileRoute } from '@tanstack/react-router';
import { z } from "zod";

import GaugeComponent from 'react-gauge-component';
import { useQuery } from '@tanstack/react-query';
import { ClimateService } from '@/client';
import { Flex, Spinner, Text } from '@chakra-ui/react';
import { useParams } from '@tanstack/react-router';

// Converts Celsius limits to Fahrenheit:
// F = C × 9/5 + 32
const toF = (c: number) => c * 9 / 5 + 32;

// --- Inside Temperature (°F) ---
export const insideTempArc = {
  width: 0.2,
  padding: 0.005,
  cornerRadius: 1,
  subArcs: [
    { limit: toF(15), color: '#EA4228', showTick: true, tooltip: { text: 'Too low temperature!' } },
    { limit: toF(17), color: '#F5CD19', showTick: true, tooltip: { text: 'Low temperature!' } },
    { limit: toF(28), color: '#5BE12C', showTick: true, tooltip: { text: 'OK temperature!' } },
    { limit: toF(30), color: '#F5CD19', showTick: true, tooltip: { text: 'High temperature!' } },
    { color: '#EA4228',           tooltip: { text: 'Too high temperature!' } },
  ]
};

export const insideTempPointer = {
  color: '#345243',
  length: 0.8,
  width: 15
};

// --- Inside Humidity (%) ---
export const insideHumidityArc = {
  width: 0.2,
  padding: 0.005,
  cornerRadius: 1,
  subArcs: [
    { limit: 30, color: '#EA4228', showTick: true, tooltip: { text: 'Too low humidity!' } },
    { limit: 40, color: '#F5CD19', showTick: true, tooltip: { text: 'Low humidity!' } },
    { limit: 60, color: '#5BE12C', showTick: true, tooltip: { text: 'OK humidity!' } },
    { limit: 70, color: '#F5CD19', showTick: true, tooltip: { text: 'High humidity!' } },
    { color: '#EA4228', tooltip: { text: 'Too high humidity!' } },
  ]
};

export const insideHumidityPointer = {
  color: '#345243',
  length: 0.8,
  width: 15
};

// --- Outside Temperature (°F) ---
export const outsideTempArc = {
  width: 0.2,
  padding: 0.005,
  cornerRadius: 1,
  subArcs: [
    { limit: toF(0),  color: '#EA4228', showTick: true, tooltip: { text: 'Freezing (Too low)!' } },
    { limit: toF(32), color: '#F5CD19', showTick: true, tooltip: { text: 'Cold (Low)!' } },
    { limit: toF(75), color: '#5BE12C', showTick: true, tooltip: { text: 'Mild (OK)!' } },
    { limit: toF(90), color: '#F5CD19', showTick: true, tooltip: { text: 'Warm (High)!' } },
    { color: '#EA4228', tooltip: { text: 'Too hot!' } },
  ]
};

export const outsideTempPointer = {
  color: '#345243',
  length: 0.8,
  width: 15
};

// --- Outside Humidity (%) ---
export const outsideHumidityArc = {
  width: 0.2,
  padding: 0.005,
  cornerRadius: 1,
  subArcs: [
    { limit: 20, color: '#EA4228', showTick: true, tooltip: { text: 'Very dry!' } },
    { limit: 40, color: '#F5CD19', showTick: true, tooltip: { text: 'Dry!' } },
    { limit: 60, color: '#5BE12C', showTick: true, tooltip: { text: 'Comfortable!' } },
    { limit: 80, color: '#F5CD19', showTick: true, tooltip: { text: 'Humid!' } },
    { color: '#EA4228', tooltip: { text: 'Very humid!' } },
  ]
};

export const outsideHumidityPointer = {
  color: '#345243',
  length: 0.8,
  width: 15
};

function ClimateDetail() {
    const { greenhouseId } = useParams({ from: '/greenhouses/$greenhouseId/climate' }) as { greenhouseId: string };
  
    const { data, isLoading, isError, error } = useQuery({
        queryKey: ['greenhouseClimate', greenhouseId],
        queryFn: () => ClimateService.greenhouseReadClimate({ greenhouseId }),
        refetchInterval: 10_000,
        retry: 3,
        staleTime: 60_000,
      })
    console.log("🌱 greenhouseId", greenhouseId)
    ;
    if (data) {
        console.log("📊 climate data", data);
    }
  if (isLoading) {
    return (
      <Flex justify="center" align="center" height="100%">
        <Spinner size="xl" />
      </Flex>
    );
  }

  if (isError) {
    return (
      <Flex justify="center" align="center" height="100%">
        <Text color="red.500">Error loading climate data: {(error as Error).message}</Text>
      </Flex>
    );
  }

  const insideTemperature = data?.temperature ?? 22.5;
  const insideHumidity = data?.humidity ?? 50;

  return (
    <Flex gap={10} justify="center" align="center" flexWrap="wrap" p={4}>
      <Flex direction="column" align="center">
        <Text fontSize="lg" mb={4}>Inside Temperature</Text>
        <GaugeComponent
          type="semicircle"
          arc={insideTempArc}
          pointer={insideTempPointer}
          labels={{
            valueLabel: { formatTextValue: (v: number) => `${v.toFixed(1)}°F` },
            tickLabels: {
              type: 'outer',
              defaultTickValueConfig: {
                formatTextValue: (v: number) => `${v.toFixed(1)}°F`,
                style: { fontSize: 10 }
              },
              ticks: [
                { value: toF(10) },
                { value: toF(22.5) },
                { value: toF(35) }
              ]
            }
          }}
          value={insideTemperature}
          minValue={toF(10)}
          maxValue={toF(35)}
        />
      </Flex>
      <Flex direction="column" align="center">
        <Text fontSize="lg" mb={4}>Inside Humidity</Text>
        <GaugeComponent
          type="semicircle"
          arc={insideHumidityArc}
          pointer={insideHumidityPointer}
          labels={{
            valueLabel: { formatTextValue: (v: number) => `${v.toFixed(1)}%` },
            tickLabels: {
              type: 'outer',
              defaultTickValueConfig: {
                formatTextValue: (v: number) => `${v.toFixed(1)}%`,
                style: { fontSize: 10 }
              },
              ticks: [{ value: 20 }, { value: 50 }, { value: 80 }]
            }
          }}
          value={insideHumidity}
          minValue={0}
          maxValue={100}
        />
      </Flex>
      <Flex direction="column" align="center">
        <Text fontSize="lg" mb={4}>Outside Temperature</Text>
        <GaugeComponent
          type="semicircle"
          arc={outsideTempArc}
          pointer={outsideTempPointer}
          labels={{
            valueLabel: { formatTextValue: (v: number) => `${v.toFixed(1)}°F` },
            tickLabels: {
              type: 'outer',
              defaultTickValueConfig: {
                formatTextValue: (v: number) => `${v.toFixed(1)}°F`,
                style: { fontSize: 10 }
              },
              ticks: [
                { value: toF(0) },
                { value: toF(50) },
                { value: toF(100) }
              ]
            }
          }}
          value={data?.outside_temperature}
          minValue={toF(0)}
          maxValue={toF(100)}
        />
      </Flex>
      <Flex direction="column" align="center">
        <Text fontSize="lg" mb={4}>Outside Humidity</Text>
        <GaugeComponent
          type="semicircle"
          arc={outsideHumidityArc}
          pointer={outsideHumidityPointer}
          labels={{
            valueLabel: { formatTextValue: (v: number) => `${v.toFixed(1)}%` },
            tickLabels: {
              type: 'outer',
              defaultTickValueConfig: {
                formatTextValue: (v: number) => `${v.toFixed(1)}%`,
                style: { fontSize: 10 }
              },
              ticks: [{ value: 20 }, { value: 50 }, { value: 80 }]
            }
          }}
          value={data?.outside_humidity}
          minValue={0}
          maxValue={100}
        />
      </Flex>
    </Flex>
  );
}

export const Route = createFileRoute('/greenhouses/$greenhouseId/climate')({
    component: ClimateDetail,
    parseParams: (raw) => z.object({ greenhouseId: z.string() }).parse(raw),
  });

export default ClimateDetail;