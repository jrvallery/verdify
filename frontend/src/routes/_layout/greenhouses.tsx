import {
  Box,
  Container,
  Flex,
  Grid,
  Heading,
  Icon,
  Text,
  VStack,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { FiCheck, FiX } from "react-icons/fi"
import { GreenhousesService } from "@/client"
import PendingItems from "@/components/Pending/PendingItems"
import AddGreenhouse from "@/components/Greenhouses/AddGreenhouse"

const PER_PAGE = 5

function getGreenhousesQueryOptions({ page }: { page: number }) {
  return {
    queryFn: () =>
      GreenhousesService.readGreenhouses({
        skip: (page - 1) * PER_PAGE,
        limit: PER_PAGE,
      }),
    queryKey: ["greenhouses", { page }],
  }
}

export const Route = createFileRoute("/_layout/greenhouses")({
  component: Greenhouses,
})

function Greenhouses() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useQuery({
    ...getGreenhousesQueryOptions({ page: 1 }),
  })

  const greenhouses = data?.data ?? []

  if (isLoading) {
    return <PendingItems />
  }

  if (error) {
    return (
      <VStack textAlign="center" gap={4} mt={8}>
        <Text fontSize="lg" color="red.500">
          Failed to load greenhouses. Please try again later.
        </Text>
      </VStack>
    )
  }

  return (
    <Container maxW="full" py={8}>
      <Flex justifyContent="space-between" alignItems="center" mb={6}>
        <VStack align="start">
          <Heading size="lg">Greenhouses Management</Heading>
          <Text color="gray.600">Manage and monitor your greenhouses efficiently.</Text>
        </VStack>
        <AddGreenhouse />
      </Flex>
      {greenhouses.length === 0 ? (
        <VStack textAlign="center" gap={4}>
          <Text fontSize="lg" color="gray.600">
            You don’t have any greenhouses yet.
          </Text>
          <Text color="gray.500">Add a new greenhouse to get started.</Text>
        </VStack>
      ) : (
        <Grid templateColumns={{ base: "1fr", md: "repeat(2, 1fr)", lg: "repeat(3, 1fr)" }} gap={6}>
          {greenhouses.map((gh) => (
            <Box
              key={gh.id}
              p={4}
              borderWidth="1px"
              borderRadius="lg"
              boxShadow="sm"
              _hover={{ boxShadow: "md", transform: "scale(1.02)", cursor: "pointer" }}
              transition="all 0.2s"
              onClick={() => navigate({ to: `/greenhouses/${gh.id}`, params: { greenhouseId: gh.id } })}
            >
              <Heading size="md" mb={2}>
                {gh.title}
              </Heading>
              <Text color="gray.600" mb={4}>
                {gh.description || "No description available."}
              </Text>
              <Flex justifyContent="space-between" alignItems="center">
                <Text fontWeight="bold" color={gh.is_active ? "green.500" : "red.500"}>
                  {gh.is_active ? "Active" : "Inactive"}
                </Text>
                <Icon as={gh.is_active ? FiCheck : FiX} boxSize={5} />
              </Flex>
            </Box>
          ))}
        </Grid>
      )}
    </Container>
  )
}

export default Greenhouses