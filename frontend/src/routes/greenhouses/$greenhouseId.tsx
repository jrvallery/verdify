// frontend/src/routes/greenhouses/$greenhouseId.tsx
import { Outlet } from '@tanstack/react-router';
import {
    Box,
    Flex,
    Spinner,
    Text,
  } from "@chakra-ui/react";
  import { createFileRoute } from "@tanstack/react-router";
  import { useQuery } from "@tanstack/react-query";
  import { z } from "zod";

  import Navbar from "@/components/Common/Navbar";
  import Sidebar from "@/components/Greenhouses/GHSidebar";
  import { GreenhousesService } from "@/client";
  //import EditGreenhouse from "@/components/Greenhouses/EditGreenhouse";

  export const Route = createFileRoute("/greenhouses/$greenhouseId")({
    component: GreenhouseDetail,
    parseParams: (raw) => z.object({ greenhouseId: z.string() }).parse(raw),
  });

  function GreenhouseDetail() {
    const { greenhouseId } = Route.useParams();
    const { data, isLoading, error } = useQuery({
      queryKey: ["greenhouse", greenhouseId],
      queryFn: () =>
        GreenhousesService.readGreenhouse({ greenhouseId }),
    });

    if (isLoading) return (
      <Flex h="100vh" align="center" justify="center">
        <Spinner size="xl" />
      </Flex>
    );
    if (error || !data) return (
      <Flex h="100vh" align="center" justify="center">
        <Text color="red.500">{error ? "Failed to load." : "Not found."}</Text>
      </Flex>
    );
    return (
        <Flex direction="column" h="100vh">
          <Navbar />
          <Flex flex="1" overflow="hidden">
            <Sidebar />
            <Box as="main" flex="1" overflowY="auto" p={{ base: 4, md: 8 }}>
              <Outlet />
            </Box>
          </Flex>
        </Flex>
      );
    }

  export default GreenhouseDetail;
