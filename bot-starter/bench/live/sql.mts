// Read-only queries against the live ScrabbleBot database's public tables
// through SpacetimeDB's HTTP SQL endpoint (no login needed).

const HOST = process.env.STDB_HOST ?? "https://maincloud.spacetimedb.com";
const DB = process.env.STDB_DB ?? "scrabblebot";

type Cell = unknown;

/** Run one SQL statement; rows come back as objects keyed by column. */
export async function sql(query: string): Promise<Record<string, Cell>[]> {
  const res = await fetch(`${HOST}/v1/database/${DB}/sql`, {
    method: "POST",
    headers: { "Content-Type": "text/plain" },
    body: query,
  });
  if (!res.ok) throw new Error(`SQL ${res.status}: ${await res.text()}`);
  const [result] = (await res.json()) as {
    schema: { elements: { name: { some?: string } }[] };
    rows: Cell[][];
  }[];
  if (!result) return [];
  const cols = result.schema.elements.map((e, i) => e.name.some ?? `c${i}`);
  return result.rows.map((r) => Object.fromEntries(cols.map((c, i) => [c, r[i]])));
}
