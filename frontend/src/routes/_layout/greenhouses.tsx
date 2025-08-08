import {
  Container,
  EmptyState,
  Flex,
  Heading,
  Table,
  VStack,
} from "@chakra-ui/react"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { FiSearch } from "react-icons/fi"
import { z } from "zod"

import { GreenhousesService } from "@/client"
import { Icon } from "@chakra-ui/react"
import { FiCheck, FiX } from "react-icons/fi"
import AddGreenhouse from "@/components/Greenhouses/AddGreenhouse"
import PendingItems from "@/components/Pending/PendingItems"
import {
  PaginationItems,
  PaginationNextTrigger,
  PaginationPrevTrigger,
  PaginationRoot,
} from "@/components/ui/pagination.tsx"

const greenhousesSearchSchema = z.object({
  page: z.number().catch(1),
})

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
  validateSearch: (search) => greenhousesSearchSchema.parse(search),
})

function GreenhousesTable() {
  const navigate = useNavigate({ from: Route.fullPath })
  const { page } = Route.useSearch()

  const { data, isLoading, isPlaceholderData } = useQuery({
    ...getGreenhousesQueryOptions({ page }),
    placeholderData: (prev) => prev,
  })

  const setPage = (page: number) =>
    navigate({
      search: { page },
    })

  const greenhouses = data?.data.slice(0, PER_PAGE) ?? []
  const count = data?.count ?? 0

  if (isLoading) {
    return <PendingItems />
  }

  if (greenhouses.length === 0) {
    return (
      <EmptyState.Root>
        <EmptyState.Content>
          <EmptyState.Indicator>
            <FiSearch />
          </EmptyState.Indicator>
          <VStack textAlign="center">
            <EmptyState.Title>You don’t have any greenhouses yet</EmptyState.Title>
            <EmptyState.Description>
              Add a new greenhouse to get started
            </EmptyState.Description>
          </VStack>
        </EmptyState.Content>
      </EmptyState.Root>
    )
  }

  return (
    <>
      <Table.Root size={{ base: "sm", md: "md" }}>
        <Table.Header>
          <Table.Row>
            <Table.ColumnHeader w="30%" fontSize="lg">Title</Table.ColumnHeader>
            <Table.ColumnHeader w="30%" fontSize="lg">Description</Table.ColumnHeader>
            <Table.ColumnHeader w="10%" fontSize="lg">Active</Table.ColumnHeader>
          </Table.Row>
        </Table.Header>
        <Table.Body>
          {greenhouses.map((gh) => (
            <Table.Row
            cursor="pointer"
            onClick={() => navigate({ to: "/greenhouses/$greenhouseId/zones", params: { greenhouseId: gh.id } })}
            key={gh.id} 
            opacity={isPlaceholderData ? 0.5 : 1}>
              <Table.Cell fontSize="lg" truncate maxW="30%">
                {gh.title}
              </Table.Cell>
              <Table.Cell
                fontSize="lg"
                color={!gh.description ? "gray" : "inherit"}
                truncate
                maxW="30%"
              >
                {gh.description || "N/A"}
              </Table.Cell>
              <Table.Cell width="10%" textAlign="center">
                {gh.is_active ? (
                  <Icon as={FiCheck} boxSize={5} color="green.500" />
                ) : (
                  <Icon as={FiX}   boxSize={5} color="red.500" />
                )}
              </Table.Cell>
            </Table.Row>
          ))}
        </Table.Body>
      </Table.Root>
      <Flex justifyContent="flex-end" mt={4}>
        <PaginationRoot
          count={count}
          pageSize={PER_PAGE}
          onPageChange={({ page }) => setPage(page)}
        >
          <Flex>
            <PaginationPrevTrigger />
            <PaginationItems />
            <PaginationNextTrigger />
          </Flex>
        </PaginationRoot>
      </Flex>
    </>
  )
}

function Greenhouses() {
  return (
    <Container maxW="full">
      <Heading size="lg" pt={12}>
        Greenhouses Management
      </Heading>
      <AddGreenhouse />
      <GreenhousesTable />
    </Container>
  )
}

export default Greenhouses