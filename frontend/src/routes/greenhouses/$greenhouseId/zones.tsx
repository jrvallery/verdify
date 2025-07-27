import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/greenhouses/$greenhouseId/zones')({
  component: () => <div>Hello /greenhouses/$greenhouseId/zones!</div>
})