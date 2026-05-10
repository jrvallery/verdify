import { PageLayout, SharedLayout } from "./quartz/cfg"
import * as Component from "./quartz/components"

const showsPlanningDate = (page: any) => /^plans\/\d{4}-\d{2}-\d{2}$/.test(page.fileData.slug)

// components shared across all pages
export const sharedPageComponents: SharedLayout = {
  head: Component.Head(),
  header: [],
  afterBody: [Component.GrafanaEmbeds()],
  footer: Component.Footer({
    links: {
      "Home": "/",
      "The Greenhouse": "/greenhouse",
      "Climate": "/start/climate",
      "Evidence": "/start/evidence",
      "Operations": "/data/operations",
      "Planning Archive": "/data/plans",
      "Intelligence": "/reference/intelligence",
      "FAQ": "/reference/faq",
      "Contact": "/start/contact",
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
    Component.ConditionalRender({
      component: Component.ContentMeta({ showDate: true }),
      condition: showsPlanningDate,
    }),
    Component.ConditionalRender({
      component: Component.ContentMeta({ showDate: false }),
      condition: (page) => !showsPlanningDate(page),
    }),
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
    Component.SiteNav(),
  ],
  right: [],
}

// components for pages that display lists of pages  (e.g. tags or folders)
export const defaultListPageLayout: PageLayout = {
  beforeBody: [Component.Breadcrumbs(), Component.ArticleTitle(), Component.ContentMeta({ showDate: false })],
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
    Component.SiteNav(),
  ],
  right: [],
}
