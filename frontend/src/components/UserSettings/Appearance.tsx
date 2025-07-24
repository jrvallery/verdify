import { Container, Heading, Stack } from "@chakra-ui/react"
import { useTheme } from "next-themes"

import { Radio, RadioGroup } from "@/components/ui/radio"

const Appearance = () => {
  const { theme, setTheme } = useTheme()
  // Always use a non-null string for the radio group value
  const currentTheme = theme ?? "system"

  return (
    <Container maxW="full">
      <Heading size="sm" py={4}>
        Appearance
      </Heading>

      <RadioGroup
        value={currentTheme}
        // Ensure setTheme only ever receives a string
        onValueChange={({ value }) => setTheme(value ?? "system")}
        colorPalette="teal"
      >
        <Stack>
          <Radio value="system">System</Radio>
          <Radio value="light">Light Mode</Radio>
          <Radio value="dark">Dark Mode</Radio>
        </Stack>
      </RadioGroup>
    </Container>
  )
}

export default Appearance

