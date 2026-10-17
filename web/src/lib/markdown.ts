/** A small Markdown subset, enough for docs/glossary.md: headings (#, ##),
 * bullet lists ("- ", continued on indented lines), paragraphs, **bold** and
 * [links](url). Everything else is plain text. */

export type Inline = { kind: "text" | "bold"; text: string } | { kind: "link"; text: string; href: string };

export type Block =
  | { kind: "heading"; level: 1 | 2; inline: Inline[] }
  | { kind: "list"; items: Inline[][] }
  | { kind: "paragraph"; inline: Inline[] };

export function parseInline(text: string): Inline[] {
  const out: Inline[] = [];
  const pattern = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0;
  for (const m of text.matchAll(pattern)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ kind: "text", text: text.slice(last, at) });
    if (m[1] !== undefined) out.push({ kind: "bold", text: m[1] });
    else out.push({ kind: "link", text: m[2] ?? "", href: m[3] ?? "" });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ kind: "text", text: text.slice(last) });
  return out;
}

export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let items: string[] | null = null;
  const flush = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", inline: parseInline(paragraph.join(" ")) });
    if (items) blocks.push({ kind: "list", items: items.map(parseInline) });
    paragraph = [];
    items = null;
  };
  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trimEnd();
    const heading = /^(#{1,2})\s+(.*)$/.exec(line);
    if (heading) {
      flush();
      const [, hashes = "#", title = ""] = heading;
      blocks.push({ kind: "heading", level: hashes.length === 1 ? 1 : 2, inline: parseInline(title) });
    } else if (line.startsWith("- ")) {
      if (paragraph.length) flush();
      (items ??= []).push(line.slice(2));
    } else if (/^\s+\S/.test(line) && items && items.length > 0) {
      items[items.length - 1] += " " + line.trim();
    } else if (line.trim() === "") {
      flush();
    } else {
      if (items) flush();
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}
