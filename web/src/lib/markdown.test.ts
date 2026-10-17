import { describe, expect, it } from "vitest";
import { parseInline, parseMarkdown } from "./markdown";

describe("parseMarkdown", () => {
  it("reads headings, lists with continued items, and paragraphs", () => {
    const blocks = parseMarkdown(
      "# Glossary\n\nIntro line\nstill intro.\n\n## Models\n\n- **H1.** Bands from\n  feedback.\n- **H2.** Rings.\n",
    );
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "paragraph", "heading", "list"]);
    const list = blocks[3];
    if (list?.kind !== "list") throw new Error("expected a list");
    expect(list.items).toHaveLength(2);
    expect(list.items[0]).toEqual([
      { kind: "bold", text: "H1." },
      { kind: "text", text: " Bands from feedback." },
    ]);
    const para = blocks[1];
    if (para?.kind !== "paragraph") throw new Error("expected a paragraph");
    expect(para.inline).toEqual([{ kind: "text", text: "Intro line still intro." }]);
  });

  it("reads links and bold within text", () => {
    expect(parseInline("see [ADR 0028](adr/0028.md) and **this**")).toEqual([
      { kind: "text", text: "see " },
      { kind: "link", text: "ADR 0028", href: "adr/0028.md" },
      { kind: "text", text: " and " },
      { kind: "bold", text: "this" },
    ]);
  });
});
