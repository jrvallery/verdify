import { Box, Flex, Icon, Text } from "@chakra-ui/react"
import { useQueryClient } from "@tanstack/react-query"
import { Link as RouterLink } from "@tanstack/react-router"
import {
    FiHome,
    FiThermometer,
    FiGrid,
    FiTool,
    FiBarChart2,
    FiSettings,
    FiUsers,
  } from "react-icons/fi";
  
import type { IconType } from "react-icons/lib"

import type { UserPublic } from "@/client"

const items = [
    { icon: FiHome, title: "Dashboard", path: "/greenhouses/$greenhouseId" },
    { icon: FiThermometer, title: "Climate", path: "/greenhouses/$greenhouseId/climate" },
    { icon: FiGrid, title: "Zones", path: "/greenhouses/$greenhouseId/zones" },
    { icon: FiTool, title: "Equipment", path: "/greenhouses/$greenhouseId/equipment" },
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

  const finalItems: Item[] = currentUser?.is_superuser
    ? [...items, { icon: FiUsers, title: "Admin", path: "/admin" }]
    : items

  const listItems = finalItems.map(({ icon, title, path }) => (
    <RouterLink key={title} to={path} onClick={onClose}>
      <Flex
        gap={4}
        px={4}
        py={2}
        _hover={{
          background: "gray.subtle",
        }}
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
      <Text fontSize="xs" px={4} py={2} fontWeight="bold">
        Menu
      </Text>
      <Box>{listItems}</Box>
    </>
  )
}

export default GHSidebarItems