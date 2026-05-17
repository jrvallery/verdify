import {
    QuartzComponent,
    QuartzComponentConstructor,
    QuartzComponentProps,
} from "./types";
import style from "./styles/siteNav.scss";

type SiteNavItem = {
    label: string;
    href?: string;
    slug?: string;
    aliases?: string[];
    exact?: boolean;
    children?: SiteNavItem[];
};

type SiteNavGroup = {
    title: string;
    links: SiteNavItem[];
};

const primaryLinks: SiteNavItem[] = [
    { label: "Home", href: "/", slug: "index", exact: true },
    {
        label: "AI Greenhouse",
        href: "/start/ai-greenhouse",
        slug: "start/ai-greenhouse",
    },
    { label: "Climate", href: "/start/climate", slug: "start/climate" },
    { label: "Evidence", href: "/start/evidence", slug: "start/evidence" },
    {
        label: "Resource Use",
        href: "/start/resource-use",
        slug: "start/resource-use",
    },
    { label: "Operations", href: "/data/operations", slug: "data/operations" },
    {
        label: "Plans",
        href: "/data/plans",
        slug: "data/plans",
        aliases: ["plans"],
        exact: true,
    },
    {
        label: "About",
        href: "/start/about",
        slug: "start/about",
        exact: true,
    },
    {
        label: "Contact",
        href: "/start/contact",
        slug: "start/contact",
        exact: true,
    },
];

const groups: SiteNavGroup[] = [
    {
        title: "Greenhouse",
        links: [
            {
                label: "Overview",
                href: "/greenhouse",
                slug: "greenhouse",
                exact: true,
            },
            {
                label: "Crops",
                children: [
                    {
                        label: "Crop Overview",
                        href: "/greenhouse/crops",
                        slug: "greenhouse/crops",
                        exact: true,
                    },
                    {
                        label: "Lettuce",
                        href: "/greenhouse/crops/lettuce",
                        slug: "greenhouse/crops/lettuce",
                    },
                    {
                        label: "Strawberries",
                        href: "/greenhouse/crops/strawberries",
                        slug: "greenhouse/crops/strawberries",
                    },
                    {
                        label: "Peppers",
                        href: "/greenhouse/crops/peppers",
                        slug: "greenhouse/crops/peppers",
                    },
                    {
                        label: "Basil",
                        href: "/greenhouse/crops/basil",
                        slug: "greenhouse/crops/basil",
                    },
                    {
                        label: "Herbs",
                        href: "/greenhouse/crops/herbs",
                        slug: "greenhouse/crops/herbs",
                    },
                    {
                        label: "Tomatoes",
                        href: "/greenhouse/crops/tomatoes",
                        slug: "greenhouse/crops/tomatoes",
                    },
                    {
                        label: "Cucumbers",
                        href: "/greenhouse/crops/cucumbers",
                        slug: "greenhouse/crops/cucumbers",
                    },
                    {
                        label: "Canna",
                        href: "/greenhouse/crops/canna",
                        slug: "greenhouse/crops/canna",
                    },
                    {
                        label: "Orchids",
                        href: "/greenhouse/crops/orchid",
                        slug: "greenhouse/crops/orchid",
                    },
                ],
            },
            {
                label: "Zones",
                children: [
                    {
                        label: "Zone Overview",
                        href: "/greenhouse/zones",
                        slug: "greenhouse/zones",
                        exact: true,
                    },
                    {
                        label: "East",
                        href: "/greenhouse/zones/east",
                        slug: "greenhouse/zones/east",
                    },
                    {
                        label: "South",
                        href: "/greenhouse/zones/south",
                        slug: "greenhouse/zones/south",
                    },
                    {
                        label: "West",
                        href: "/greenhouse/zones/west",
                        slug: "greenhouse/zones/west",
                    },
                    {
                        label: "North",
                        href: "/greenhouse/zones/north",
                        slug: "greenhouse/zones/north",
                    },
                    {
                        label: "Center",
                        href: "/greenhouse/zones/center",
                        slug: "greenhouse/zones/center",
                    },
                ],
            },
            {
                label: "Equipment",
                href: "/greenhouse/equipment",
                slug: "greenhouse/equipment",
            },
            {
                label: "Hydroponics",
                href: "/greenhouse/hydroponics",
                slug: "greenhouse/hydroponics",
            },
            {
                label: "Lighting",
                href: "/greenhouse/lighting",
                slug: "greenhouse/lighting",
            },
            {
                label: "Soil",
                href: "/greenhouse/soil",
                slug: "greenhouse/soil",
            },
            {
                label: "Cameras",
                href: "/greenhouse/cameras",
                slug: "greenhouse/cameras",
            },
            {
                label: "Structure",
                href: "/greenhouse/structure",
                slug: "greenhouse/structure",
            },
        ],
    },
    {
        title: "Data",
        links: [
            {
                label: "Planning Quality",
                href: "/data/planning-quality",
                slug: "data/planning-quality",
            },
            {
                label: "Baseline vs Iris",
                href: "/data/baseline-vs-iris",
                slug: "data/baseline-vs-iris",
            },
            {
                label: "Economics",
                href: "/data/economics",
                slug: "data/economics",
            },
            {
                label: "Forecast",
                href: "/data/forecast",
                slug: "data/forecast",
                exact: true,
            },
            {
                label: "Slack Ops",
                href: "/start/slack-ops",
                slug: "start/slack-ops",
                exact: true,
            },
        ],
    },
    {
        title: "Reference",
        links: [
            {
                label: "Intelligence",
                href: "/reference/intelligence",
                slug: "reference/intelligence",
                exact: true,
            },
            {
                label: "Planning Loop",
                href: "/reference/planning-loop",
                slug: "reference/planning-loop",
            },
            {
                label: "AI Tunables",
                href: "/reference/ai-tunables",
                slug: "reference/ai-tunables",
            },
            {
                label: "Context Window",
                href: "/reference/context-window",
                slug: "reference/context-window",
            },
            {
                label: "Inference",
                href: "/reference/inference",
                slug: "reference/inference",
            },
            {
                label: "Agent Fleet",
                href: "/reference/openclaw",
                slug: "reference/openclaw",
            },
            {
                label: "Architecture",
                href: "/reference/architecture",
                slug: "reference/architecture",
            },
            {
                label: "Safety",
                href: "/reference/safety",
                slug: "reference/safety",
            },
            {
                label: "Data Model",
                href: "/reference/data-model",
                slug: "reference/data-model",
            },
            {
                label: "Known Limits",
                href: "/reference/known-limits",
                slug: "reference/known-limits",
            },
            {
                label: "GitHub",
                href: "https://github.com/jrvallery/verdify",
            },
            { label: "FAQ", href: "/reference/faq", slug: "reference/faq" },
        ],
    },
];

function normalizeSlug(slug: string | undefined) {
    return (slug ?? "").replace(/\/index$/, "").replace(/^\//, "");
}

function isActiveItem(currentSlug: string, item: SiteNavItem): boolean {
    if (!item.slug) return false;
    const current = normalizeSlug(currentSlug);
    const targets = [item.slug, ...(item.aliases ?? [])].map(normalizeSlug);
    if (targets.includes("index")) {
        return current === "" || current === "index";
    }
    if (item.exact) {
        return targets.some(
            (target) =>
                current === target ||
                (target === "plans" && current.startsWith("plans/")),
        );
    }
    return targets.some(
        (target) => current === target || current.startsWith(`${target}/`),
    );
}

function isActiveBranch(currentSlug: string, item: SiteNavItem): boolean {
    return (
        isActiveItem(currentSlug, item) ||
        Boolean(
            item.children?.some((child) => isActiveBranch(currentSlug, child)),
        )
    );
}

function activeSectionLabel(currentSlug: string) {
    if (primaryLinks.some((link) => isActiveItem(currentSlug, link)))
        return "Primary";
    return (
        groups.find((group) =>
            group.links.some((link) => isActiveBranch(currentSlug, link)),
        )?.title ?? "Menu"
    );
}

function renderItem(currentSlug: string, item: SiteNavItem, child = false) {
    const isActive = isActiveItem(currentSlug, item);
    const branchActive = isActiveBranch(currentSlug, item);

    if (item.children?.length) {
        return (
            <li
                class={
                    child
                        ? "site-nav__child site-nav__branch-item"
                        : "site-nav__item site-nav__branch-item"
                }
            >
                <details class="site-nav__branch" open={branchActive}>
                    <summary>
                        <span>{item.label}</span>
                        <span
                            class="site-nav__chevron"
                            aria-hidden="true"
                        ></span>
                    </summary>
                    <ul class="site-nav__children">
                        {item.children.map((nested) =>
                            renderItem(currentSlug, nested, true),
                        )}
                    </ul>
                </details>
            </li>
        );
    }

    return (
        <li class={child ? "site-nav__child" : "site-nav__item"}>
            <a href={item.href ?? "#"} class={isActive ? "active" : undefined}>
                {item.label}
            </a>
        </li>
    );
}

function renderNavPanel(currentSlug: string, idPrefix: string) {
    return (
        <div class="site-nav__panel">
            <section
                class="site-nav__primary"
                aria-labelledby={`${idPrefix}-primary`}
            >
                <h2 id={`${idPrefix}-primary`}>Primary</h2>
                <ul>
                    {primaryLinks.map((link) => renderItem(currentSlug, link))}
                </ul>
            </section>
            {groups.map((group) => (
                <details
                    class="site-nav__group"
                    open
                >
                    <summary>
                        <span>{group.title}</span>
                        <span
                            class="site-nav__chevron"
                            aria-hidden="true"
                        ></span>
                    </summary>
                    <ul>
                        {group.links.map((link) =>
                            renderItem(currentSlug, link),
                        )}
                    </ul>
                </details>
            ))}
        </div>
    );
}

const SiteNav: QuartzComponent = ({ fileData }: QuartzComponentProps) => {
    const currentSlug = fileData.slug ?? "";
    const label = activeSectionLabel(currentSlug);

    return (
        <nav class="site-nav" aria-label="Site navigation">
            <div class="site-nav__desktop">
                {renderNavPanel(currentSlug, "site-nav-desktop")}
            </div>
            <details class="site-nav__mobile">
                <summary>
                    <span class="site-nav__menu-label">Menu</span>
                    <span class="site-nav__menu-current">{label}</span>
                    <span class="site-nav__chevron" aria-hidden="true"></span>
                </summary>
                {renderNavPanel(currentSlug, "site-nav-mobile")}
            </details>
        </nav>
    );
};

SiteNav.css = style;
SiteNav.afterDOMLoaded = `
document.addEventListener("click", (event) => {
  const target = event.target
  if (!(target instanceof Element)) return
  const link = target.closest(".site-nav__mobile a")
  if (!link) return
  const mobileNav = document.querySelector(".site-nav__mobile")
  if (mobileNav instanceof HTMLDetailsElement) mobileNav.open = false
})

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return
  const mobileNav = document.querySelector(".site-nav__mobile")
  if (mobileNav instanceof HTMLDetailsElement) mobileNav.open = false
})
`;

export default (() => SiteNav) satisfies QuartzComponentConstructor;
