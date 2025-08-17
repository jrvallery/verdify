import { Box, Flex, Icon, Text } from "@chakra-ui/react"
import { useQueryClient, useQuery } from "@tanstack/react-query"
import { Link as RouterLink, useParams } from "@tanstack/react-router"
import {
    FiHome,
    FiThermometer,
    FiGrid,
    FiTool,
    FiBarChart2,
    FiSettings,
    FiUsers,
  } from "react-icons/fi";

import { GreenhousesService } from "@/client"
import type { IconType } from "react-icons/lib"

import type { UserPublic } from "@/client"

const items = [
    { icon: FiHome, title: "greenhouseName", path: "/greenhouses/$greenhouseId" },
    { icon: FiGrid, title: "Zones", path: "/greenhouses/$greenhouseId/zones" },
    { icon: FiThermometer, title: "Climate", path: "/greenhouses/$greenhouseId/climate" },
    { icon: FiTool, title: "Controller", path: "/greenhouses/$greenhouseId/controller" },
    { icon: FiBarChart2, title: "Graphs", path: "/greenhouses/$greenhouseId/graphs" },
    { icon: FiSettings, title: "Settings", path: "/greenhouses/$greenhouseId/settings" },
]

interface SidebarItemsProps {
  onClose?: () => void
}

interface Item {
  icon: IconType
  title: string
  path: string
}

const GHSidebarItems = ({ onClose }: SidebarItemsProps) => {
  const queryClient = useQueryClient()
  const currentUser = queryClient.getQueryData<UserPublic>(["currentUser"])

  // Get greenhouseId from route and fetch greenhouse
  const { greenhouseId } = useParams({ from: "/greenhouses/$greenhouseId" })
  const { data: greenhouse } = useQuery({
    queryKey: ["greenhouse", greenhouseId],
    queryFn: () => GreenhousesService.readGreenhouse({ greenhouseId }),
    enabled: !!greenhouseId,
  })

  // Exclude the first item (dashboard link) and keep the rest
  const baseMenu: Item[] = items.slice(1)

  const finalItems: Item[] = currentUser?.is_superuser
    ? [...baseMenu, { icon: FiUsers, title: "Admin", path: "/admin" }]
    : baseMenu

  const listItems = finalItems.map(({ icon, title, path }) => (
    <RouterLink key={title} to={path} onClick={onClose}>
      <Flex
        gap={4}
        px={4}
        py={2}
        _hover={{ background: "gray.subtle" }}
        alignItems="center"
        fontSize="sm"
      >
        <Icon as={icon} alignSelf="center" />
        <Text ml={2}>{title}</Text>
      </Flex>
    </RouterLink>
  ))

  return (
    <>
      <Box px={4} py={3}>
        <Text fontSize="lg" fontWeight="bold" truncate>
          {greenhouse?.title ?? "Greenhouse"}
        </Text>
      </Box>
      <Box>{listItems}</Box>
    </>
  )
}

export default GHSidebarItems
