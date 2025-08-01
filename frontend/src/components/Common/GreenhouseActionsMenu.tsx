import { IconButton } from "@chakra-ui/react"
import { BsThreeDotsVertical } from "react-icons/bs"
import { MenuContent, MenuRoot, MenuTrigger } from "../ui/menu"

import type { GreenhousePublic } from "@/client"
import DeleteGreenhouse from "../Greenhouses/DeleteGreenhouse"
import EditGreenhouse from "../Greenhouses/EditGreenhouse"

interface GreenhouseActionsMenuProps {
  greenhouse: GreenhousePublic
}

export const GreenhouseActionsMenu = ({
  greenhouse,
}: GreenhouseActionsMenuProps) => {
  return (
    <MenuRoot>
      <MenuTrigger asChild>
        <IconButton variant="ghost" color="inherit" aria-label="Actions">
          <BsThreeDotsVertical />
        </IconButton>
      </MenuTrigger>
      <MenuContent>
        <EditGreenhouse greenhouse={greenhouse} />
        <DeleteGreenhouse id={greenhouse.id} />
      </MenuContent>
    </MenuRoot>
  )
}
