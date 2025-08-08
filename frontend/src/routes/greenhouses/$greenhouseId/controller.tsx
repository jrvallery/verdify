import { createFileRoute } from '@tanstack/react-router'
import {
  Box,
  Container,
  Flex,
  Heading,
  Table,
  Text,
  Badge,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"

import { ControllersService, SensorsService, SensorPublic, ControllerPublic } from "@/client"
import AddController from "@/components/Controllers/AddController"
import DeleteController from "@/components/Controllers/DeleteController"
import AddSensor from "@/components/Sensors/AddSensor"
import DeleteSensor from "@/components/Sensors/DeleteSensor"

export const Route = createFileRoute('/greenhouses/$greenhouseId/controller')({
  component: Controller
})

function Controller() {
  const { greenhouseId } = Route.useParams()

  const {
    data: controllers,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["controllers", greenhouseId],
    queryFn: () => ControllersService.listControllers({ greenhouseId }),
  })

  if (isLoading) return <Text>Loading...</Text>
  if (isError) return <Text>Error loading controllers</Text>

  return (
    <Container maxW="full">
      <Heading size="lg" textAlign={{ base: "center", md: "left" }} pt={12}>
        Controllers Management
      </Heading>

      <AddController greenhouseId={greenhouseId} />

      {controllers?.map((controller: ControllerPublic) => (
        <Box 
          key={controller.id} 
          border="2px" 
          borderColor={{ base: "gray.200", _dark: "gray.600" }}
          rounded="xl" 
          p={6} 
          mb={6}
          shadow="md"
          bg={{ base: "white", _dark: "gray.800" }}
          _hover={{ 
            shadow: "lg",
            borderColor: { base: "gray.300", _dark: "gray.500" }
          }}
        >
          <Flex justify="space-between" align="center" mb={4}>
            <Box>
              <Heading size="lg" color={{ base: "gray.800", _dark: "gray.100" }}>
                {controller.name}
              </Heading>
              {controller.model && (
                <Text color={{ base: "gray.600", _dark: "gray.400" }}>
                  {controller.model}
                </Text>
              )}
            </Box>
            <Flex gap={2}>
              <AddSensor controllerId={controller.id} />
              <DeleteController id={controller.id} />
            </Flex>
          </Flex>

          <ControllerSensors controllerId={controller.id} greenhouseId={greenhouseId} />
        </Box>
      ))}
    </Container>
  )
}

function ControllerSensors({ controllerId, greenhouseId }: { controllerId: string, greenhouseId: string }) {
  const {
    data: sensors,
    isLoading,
  } = useQuery({
    queryKey: ["sensors", controllerId],
    queryFn: () => SensorsService.listSensors({ controllerId, greenhouseId } as any),
  })

  const getSensorTypeColor = (type: string) => {
    const colors = {
      temperature: "red",
      humidity: "blue",
      co2: "green",
      light: "yellow",
      soil_moisture: "brown",
    }
    return colors[type as keyof typeof colors] || "gray"
  }

  if (isLoading) return <Text>Loading sensors...</Text>

  return (
    <Box>
      <Text 
        fontWeight="bold" 
        mb={2}
        color={{ base: "gray.700", _dark: "gray.200" }}
      >
        Sensors ({sensors?.length || 0})
      </Text>
      {sensors && sensors.length > 0 ? (
        <Box 
          overflowX="auto"
          bg={{ base: "gray.50", _dark: "gray.900" }}
          rounded="lg"
          p={2}
        >
          <Table.Root size="sm">
            <Table.Header>
              <Table.Row>
                <Table.ColumnHeader color={{ base: "gray.600", _dark: "gray.300" }}>
                  Name
                </Table.ColumnHeader>
                <Table.ColumnHeader color={{ base: "gray.600", _dark: "gray.300" }}>
                  Type
                </Table.ColumnHeader>
                <Table.ColumnHeader color={{ base: "gray.600", _dark: "gray.300" }}>
                  Model
                </Table.ColumnHeader>
                <Table.ColumnHeader color={{ base: "gray.600", _dark: "gray.300" }}>
                  Value
                </Table.ColumnHeader>
                <Table.ColumnHeader color={{ base: "gray.600", _dark: "gray.300" }}>
                  Unit
                </Table.ColumnHeader>
                <Table.ColumnHeader color={{ base: "gray.600", _dark: "gray.300" }}>
                  Actions
                </Table.ColumnHeader>
              </Table.Row>
            </Table.Header>
            <Table.Body>
              {sensors.map((sensor: SensorPublic) => (
                <Table.Row 
                  key={sensor.id}
                  _hover={{ 
                    bg: { base: "gray.100", _dark: "gray.700" }
                  }}
                >
                  <Table.Cell color={{ base: "gray.800", _dark: "gray.200" }}>
                    {sensor.name}
                  </Table.Cell>
                  <Table.Cell>
                    <Badge colorPalette={getSensorTypeColor(sensor.type)}>
                      {sensor.type}
                    </Badge>
                  </Table.Cell>
                  <Table.Cell color={{ base: "gray.600", _dark: "gray.400" }}>
                    {sensor.model || "-"}
                  </Table.Cell>
                  <Table.Cell color={{ base: "gray.600", _dark: "gray.400" }}>
                    {sensor.value || "-"}
                  </Table.Cell>
                  <Table.Cell color={{ base: "gray.600", _dark: "gray.400" }}>
                    {sensor.unit || "-"}
                  </Table.Cell>
                  <Table.Cell>
                    <DeleteSensor id={sensor.id} controllerId={controllerId} />
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table.Root>
        </Box>
      ) : (
        <Text color={{ base: "gray.500", _dark: "gray.400" }}>
          No sensors added yet
        </Text>
      )}
    </Box>
  )
}