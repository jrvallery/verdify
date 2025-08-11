import { createFileRoute } from "@tanstack/react-router";
import GHSettings from "@/components/Greenhouses/GHSettings";

export const Route = createFileRoute("/greenhouses/$greenhouseId/settings")({
  component: GHSettings,
});