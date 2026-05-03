import { QuartzComponent, QuartzComponentConstructor, QuartzComponentProps } from "./types"

type NavLink = {
  label: string
  href: string
  slug: string
  exact?: boolean
}

type NavGroup = {
  title: string
  links: NavLink[]
}

const groups: NavGroup[] = [
  {
    title: "Start",
    links: [
      { label: "Overview", href: "/", slug: "index", exact: true },
      { label: "AI Greenhouse", href: "/ai-greenhouse", slug: "ai-greenhouse" },
      { label: "The Greenhouse", href: "/greenhouse", slug: "greenhouse", exact: true },
      { label: "Climate", href: "/climate", slug: "climate", exact: true },
      { label: "Evidence", href: "/evidence", slug: "evidence", exact: true },
      { label: "Planning Archive", href: "/plans", slug: "plans", exact: true },
    ],
  },
  {
    title: "Greenhouse",
    links: [
      { label: "Crops", href: "/greenhouse/crops", slug: "greenhouse/crops" },
      { label: "Zones", href: "/greenhouse/zones", slug: "greenhouse/zones" },
      { label: "Equipment", href: "/greenhouse/equipment", slug: "greenhouse/equipment" },
      { label: "Hydroponics", href: "/greenhouse/hydroponics", slug: "greenhouse/hydroponics" },
      { label: "Structure", href: "/greenhouse/structure", slug: "greenhouse/structure" },
    ],
  },
  {
    title: "Data",
    links: [
      { label: "Planning Loop", href: "/intelligence/planning", slug: "intelligence/planning" },
      { label: "Planning Quality", href: "/evidence/planning-quality", slug: "evidence/planning-quality" },
      { label: "Operations", href: "/evidence/operations", slug: "evidence/operations" },
      { label: "Economics", href: "/evidence/economics", slug: "evidence/economics" },
      { label: "Forecast", href: "/forecast", slug: "forecast" },
    ],
  },
  {
    title: "Reference",
    links: [
      { label: "Intelligence", href: "/intelligence", slug: "intelligence", exact: true },
      { label: "Architecture", href: "/intelligence/architecture", slug: "intelligence/architecture" },
      { label: "Data Model", href: "/intelligence/data", slug: "intelligence/data" },
      { label: "Lessons", href: "/greenhouse/lessons", slug: "greenhouse/lessons" },
      { label: "About", href: "/about", slug: "about" },
    ],
  },
]

function isActive(currentSlug: string, link: NavLink): boolean {
  if (link.exact) {
    return currentSlug === link.slug || (link.slug === "index" && currentSlug === "")
  }
  return currentSlug === link.slug || currentSlug.startsWith(`${link.slug}/`)
}

const SiteNav: QuartzComponent = ({ fileData }: QuartzComponentProps) => {
  const currentSlug = fileData.slug ?? ""

  return (
    <nav class="site-nav" aria-label="Site navigation">
      <details open>
        <summary>Navigation</summary>
        <div class="site-nav__groups">
          {groups.map((group) => (
            <section class="site-nav__group" aria-labelledby={`site-nav-${group.title.toLowerCase()}`}>
              <h2 id={`site-nav-${group.title.toLowerCase()}`}>{group.title}</h2>
              <ul>
                {group.links.map((link) => (
                  <li>
                    <a href={link.href} class={isActive(currentSlug, link) ? "active" : undefined}>
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </details>
    </nav>
  )
}

SiteNav.css = `
.site-nav {
  display: flex;
  flex-direction: column;
  overflow: auto;
  min-height: 0;
  padding-bottom: 1rem;
}

.site-nav details {
  display: block;
}

.site-nav summary {
  display: none;
}

.site-nav__groups {
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
}

.site-nav__group h2 {
  margin: 0 0 0.35rem;
  color: var(--gray);
  font-family: var(--headerFont);
  font-size: 0.74rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  line-height: 1.2;
  text-transform: uppercase;
}

.site-nav__group ul {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  list-style: none;
  margin: 0;
  padding: 0;
}

.site-nav__group a {
  display: block;
  border-left: 3px solid transparent;
  border-radius: 0 5px 5px 0;
  color: var(--dark);
  font-size: 0.95rem;
  line-height: 1.25;
  opacity: 0.78;
  padding: 0.35rem 0.55rem 0.35rem 0.65rem;
  text-decoration: none;
}

.site-nav__group a:hover {
  background: var(--highlight);
  color: var(--tertiary);
  opacity: 1;
}

.site-nav__group a.active {
  background: var(--highlight);
  border-left-color: var(--tertiary);
  color: var(--tertiary);
  font-weight: 700;
  opacity: 1;
}

@media all and (max-width: 800px) {
  .sidebar.left:has(.site-nav) {
    align-items: center;
    flex-wrap: wrap;
    row-gap: 0.75rem;
  }

  .site-nav {
    flex: 1 0 100%;
    order: 10;
    overflow: visible;
    padding-bottom: 0;
  }

  .site-nav details {
    border-top: 1px solid var(--lightgray);
    padding-top: 0.75rem;
  }

  .site-nav summary {
    border: 1px solid var(--lightgray);
    border-radius: 6px;
    color: var(--dark);
    cursor: pointer;
    display: block;
    font-family: var(--headerFont);
    font-size: 0.95rem;
    font-weight: 700;
    list-style: none;
    padding: 0.35rem 0.6rem;
    width: max-content;
  }

  .site-nav summary::-webkit-details-marker {
    display: none;
  }

  .site-nav__groups {
    display: grid;
    gap: 0.9rem 1rem;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    margin-top: 0.75rem;
  }

  .site-nav__group a {
    padding: 0.33rem 0.5rem;
  }
}
`

export default (() => SiteNav) satisfies QuartzComponentConstructor
