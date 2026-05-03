import { FilePath, joinSegments } from "../../util/path"
import { QuartzEmitterPlugin } from "../types"
import fs from "fs"

export const RobotsTxt: QuartzEmitterPlugin = () => ({
  name: "RobotsTxt",
  async *emit({ argv, cfg }) {
    const baseUrl = cfg.configuration.baseUrl ?? "verdify.ai"
    const dest = joinSegments(argv.output, "robots.txt") as FilePath
    const body = [
      "User-agent: *",
      "Allow: /",
      "Disallow: /static/vision/",
      "Disallow: /greenhouse/lessons/raw",
      `Sitemap: https://${baseUrl}/sitemap.xml`,
      "",
    ].join("\n")
    await fs.promises.writeFile(dest, body)
    yield dest
  },
  async *partialEmit() {},
})
