import { Flex, Image, useBreakpointValue } from "@chakra-ui/react"
import { Link } from "@tanstack/react-router"

import VerdifyLogo from '../../assets/images/logo.svg'
import UserMenu from "./UserMenu"

function Navbar() {
  const display = useBreakpointValue({ base: "none", md: "flex" })

  return (
    <Flex
      display={display}
      justify="space-between"
      position="sticky"
      color="white"
      align="center"
      bg="bg.muted"
      w="100%"
      top={0}
      p={4}
    >
      <Link to="/">
        <Image src={VerdifyLogo} alt="Verdify logo" w = "300px" h = "auto" px={2} />
      </Link>
      <Flex gap={2} alignItems="center">
        <UserMenu />
      </Flex>
    </Flex>
  )
}

export default Navbar
