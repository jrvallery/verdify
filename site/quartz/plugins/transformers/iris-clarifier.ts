import { Root } from "hast";
import { QuartzTransformerPlugin } from "../types";

const IRIS_RE = /\bIris\b/;
const CLARIFIED_IRIS = "Iris (our OpenClaw AI agent)";
const SKIP_TAGS = new Set([
    "a",
    "code",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "kbd",
    "pre",
    "samp",
    "script",
    "style",
    "svg",
    "table",
]);
const SKIP_CLASSES = new Set(["metric-card"]);

type HastNode = {
    type?: string;
    tagName?: string;
    value?: string;
    properties?: Record<string, unknown>;
    children?: HastNode[];
};

function classNames(properties?: Record<string, unknown>): string[] {
    const raw = properties?.className ?? properties?.class;
    if (Array.isArray(raw)) return raw.map(String);
    if (typeof raw === "string") return raw.split(/\s+/);
    return [];
}

function isAlreadyClear(value: string, index: number): boolean {
    const after = value.slice(index + "Iris".length);
    return (
        /^\s*\(/.test(after) ||
        /^,\s*(an|our|Verdify's)\s+OpenClaw\b/i.test(after) ||
        /^ is Verdify's OpenClaw\b/i.test(after)
    );
}

function clarifyText(value: string): {
    value: string;
    changed: boolean;
    alreadyClear: boolean;
} {
    const match = IRIS_RE.exec(value);
    if (!match) return { value, changed: false, alreadyClear: false };
    if (isAlreadyClear(value, match.index))
        return { value, changed: false, alreadyClear: true };

    return {
        value: `${value.slice(0, match.index)}${CLARIFIED_IRIS}${value.slice(match.index + match[0].length)}`,
        changed: true,
        alreadyClear: false,
    };
}

export const IrisClarifier: QuartzTransformerPlugin = () => {
    return {
        name: "IrisClarifier",
        htmlPlugins() {
            return [
                () => {
                    return (tree: Root) => {
                        let done = false;

                        function visit(
                            node: HastNode,
                            skipped = false,
                            insideParagraph = false,
                        ): void {
                            if (done) return;

                            if (node.type === "text") {
                                if (
                                    !skipped &&
                                    insideParagraph &&
                                    typeof node.value === "string" &&
                                    IRIS_RE.test(node.value)
                                ) {
                                    const result = clarifyText(node.value);
                                    if (result.changed) {
                                        node.value = result.value;
                                        done = true;
                                    } else if (result.alreadyClear) {
                                        done = true;
                                    }
                                }
                                return;
                            }

                            const nodeClasses = classNames(node.properties);
                            const isSkipped =
                                skipped ||
                                (node.type === "element" &&
                                    typeof node.tagName === "string" &&
                                    SKIP_TAGS.has(node.tagName)) ||
                                nodeClasses.some((className) =>
                                    SKIP_CLASSES.has(className),
                                ) ||
                                node.properties?.ariaHidden === true ||
                                node.properties?.ariaHidden === "true" ||
                                node.properties?.["aria-hidden"] === true ||
                                node.properties?.["aria-hidden"] === "true";
                            const isParagraph =
                                insideParagraph ||
                                (node.type === "element" &&
                                    typeof node.tagName === "string" &&
                                    node.tagName === "p");

                            if (Array.isArray(node.children)) {
                                for (const child of node.children) {
                                    visit(child, isSkipped, isParagraph);
                                    if (done) break;
                                }
                            }
                        }

                        visit(tree as HastNode);
                    };
                },
            ];
        },
    };
};
