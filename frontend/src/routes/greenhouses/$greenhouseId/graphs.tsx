import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/greenhouses/$greenhouseId/graphs')({
  component: () => <div>Hello /greenhouses/$greenhouseId/graphs!</div>
})