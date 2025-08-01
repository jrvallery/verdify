import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/greenhouses/$greenhouseId/settings')({
  component: () => <div>Hello /greenhouses/$greenhouseId/settings!</div>
})