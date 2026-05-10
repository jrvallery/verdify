import { QuartzComponentConstructor } from "./types";
import style from "./styles/siteNav.scss";

const groups = [
    {
        title: "Start",
        links: [
            ["Home", "/"],
            ["AI Greenhouse", "/start/ai-greenhouse/"],
            ["Resource Use", "/start/resource-use/"],
            ["The Greenhouse", "/greenhouse/"],
            ["Climate", "/start/climate/"],
            ["Evidence", "/start/evidence/"],
            ["Slack Ops", "/start/slack-ops/"],
            ["Planning Archive", "/data/plans/"],
            ["About", "/start/about/"],
            ["Contact", "/start/contact/"],
        ],
    },
    {
        title: "Greenhouse",
        links: [
            ["Crops", "/greenhouse/crops/"],
            ["Zones", "/greenhouse/zones/"],
            ["Equipment", "/greenhouse/equipment/"],
            ["Hydroponics", "/greenhouse/hydroponics/"],
            ["Structure", "/greenhouse/structure/"],
        ],
    },
    {
        title: "Data",
        links: [
            ["Operations", "/data/operations/"],
            ["Planning Quality", "/data/planning-quality/"],
            ["Baseline vs Iris", "/data/baseline-vs-iris/"],
            ["Economics", "/data/economics/"],
            ["Forecast", "/data/forecast/"],
        ],
    },
    {
        title: "Reference",
        links: [
            ["Intelligence", "/reference/intelligence/"],
            ["Planning Loop", "/reference/planning-loop/"],
            ["OpenClaw", "/reference/openclaw/"],
            ["Inference", "/reference/inference/"],
            ["Context Window", "/reference/context-window/"],
            ["Architecture", "/reference/architecture/"],
            ["Safety", "/reference/safety/"],
            ["Data Model", "/reference/data-model/"],
            ["Build Notes", "/reference/build-notes/"],
            ["Known Limits", "/reference/known-limits/"],
            ["Related Work", "/reference/related-work/"],
            ["FAQ", "/reference/faq/"],
            ["Lessons", "/reference/lessons/"],
        ],
    },
];

export default (() => {
    function SiteNav() {
        return (
            <nav class="site-nav" aria-label="Primary">
                {groups.map((group) => (
                    <section>
                        <h2>{group.title}</h2>
                        <ul>
                            {group.links.map(([label, href]) => (
                                <li>
                                    <a href={href}>{label}</a>
                                </li>
                            ))}
                        </ul>
                    </section>
                ))}
            </nav>
        );
    }

    SiteNav.css = style;
    return SiteNav;
}) satisfies QuartzComponentConstructor;
