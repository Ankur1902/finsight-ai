/** Transform citation text into scoped links, without touching code or existing links. */
export type CitationNode = {
  type: string;
  value?: string;
  url?: string;
  children?: CitationNode[];
};
export type CitationOptions = { sourceIds: number[]; prefix: string };

export function citationAnchor(prefix: string, id: number): string {
  return `#${prefix}-source-${id}`;
}

export function remarkCitations(options: CitationOptions) {
  const valid = new Set(options.sourceIds);
  return (tree: CitationNode) => {
    function walk(node: CitationNode) {
      if (
        !node.children ||
        ["link", "linkReference", "image", "code", "inlineCode"].includes(
          node.type,
        )
      )
        return;
      node.children = node.children.flatMap((child) => {
        if (child.type !== "text" || !child.value) {
          walk(child);
          return [child];
        }
        const pieces: CitationNode[] = [];
        const pattern = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
        let cursor = 0;
        for (const match of child.value.matchAll(pattern)) {
          const offset = match.index!;
          if (offset > cursor)
            pieces.push({
              type: "text",
              value: child.value.slice(cursor, offset),
            });
          const ids = match[1].split(",").map((id) => Number(id.trim()));
          // Unknown IDs remain visible text, never clickable fabricated sources.
          if (!ids.every((id) => Number.isSafeInteger(id) && valid.has(id))) {
            pieces.push({ type: "text", value: match[0] });
          } else {
            ids.forEach((id, i) => {
              if (i) pieces.push({ type: "text", value: " " });
              pieces.push({
                type: "link",
                url: citationAnchor(options.prefix, id),
                children: [{ type: "text", value: `[${id}]` }],
              });
            });
          }
          cursor = offset + match[0].length;
        }
        if (cursor < child.value.length)
          pieces.push({ type: "text", value: child.value.slice(cursor) });
        return pieces.length ? pieces : [child];
      });
    }
    walk(tree);
  };
}

/** Syntactic references only; this deliberately does not claim semantic support. */
export function citedSourceIds(answer: string, sourceIds: number[]): number[] {
  const prose = answer.replace(/```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`]*`/g, "");
  const valid = new Set(sourceIds);
  return Array.from(
    new Set(
      [...prose.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]/g)]
        .flatMap((match) =>
          match[1].split(",").map((value) => Number(value.trim())),
        )
        .filter((id) => valid.has(id)),
    ),
  );
}
