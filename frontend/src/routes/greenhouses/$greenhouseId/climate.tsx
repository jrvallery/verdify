import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/greenhouses/$greenhouseId/climate')({
  component: () => <div>Hello /greenhouses/$greenhouseId/climate!</div>
})