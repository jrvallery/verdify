import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/greenhouses/$greenhouseId/equipment')({
  component: () => <div>Hello /greenhouses/$greenhouseId/equipment!</div>
})