import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"

// Shared explorer config — hide individual plan files from nav
const explorerOpts = {
  folderDefaultState: "open" as const,
  folderClickBehavior: "link" as const,
  filterFn: (node: any) => {
    // Hide individual date-named plan files (e.g. plans/2026-03-31)
    // Keep the "plans" folder itself visible as a link to the index
    if (node.slugSegment && /^\d{4}-\d{2}-\d{2}$/.test(node.slugSegment)) {
      return false
    }
    return true
  },
  sortFn: (a: any, b: any) => {
    if ((!a.isFolder && !b.isFolder) || (a.isFolder && b.isFolder)) {
      return a.displayName.localeCompare(b.displayName, undefined, {
        numeric: true,
        sensitivity: "base",
      })
    }
    return a.isFolder ? -1 : 1
  },
}

// components shared across all pages
export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  afterBody: [Component.GrafanaEmbeds()],
  footer: Component.Footer({
    links: {
      "Home": "/",
      "The Greenhouse": "/greenhouse",
      "Climate": "/climate",
      "Intelligence": "/intelligence",
      "Evidence": "/evidence",
    },
  }),
}

// components for pages that display a single page (e.g. a single note)
export const defaultContentPageLayout: PageLayout = {
  beforeBody: [
    Component.ConditionalRender({
      component: Component.Breadcrumbs(),
      condition: (page) => page.fileData.slug !== "index",
    }),
    Component.ArticleTitle(),
    Component.ContentMeta(),
    Component.TagList(),
  ],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
        { Component: Component.ReaderMode() },
      ],
    }),
    Component.Explorer(explorerOpts),
  ],
  right: [],
}

// components for pages that display lists of pages  (e.g. tags or folders)
export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.Breadcrumbs(), Component.ArticleTitle(), Component.ContentMeta()],
  left: [
    Component.PageTitle(),
    Component.MobileOnly(Component.Spacer()),
    Component.Flex({
      components: [
        {
          Component: Component.Search(),
          grow: true,
        },
        { Component: Component.Darkmode() },
      ],
    }),
    Component.Explorer(explorerOpts),
  ],
  right: [],
}
