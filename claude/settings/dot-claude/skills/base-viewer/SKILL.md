---
name: base-viewer
description: Render Obsidian Base views as markdown tables by reading the .base file, finding matching notes via its filters, extracting frontmatter properties, and displaying the data in the column order defined by each view. Use when the user asks to see, show, display, preview, or render a .base file's contents or views, or wants to know what a base view looks like.
---

# Base Viewer Skill

Reconstruct what an Obsidian Base view looks like by querying the vault's files and rendering markdown tables.

## When to use

- User asks to "see", "show", "display", "preview", or "render" a `.base` file or its views
- User asks what a base view looks like or what data it contains
- User wants to inspect the actual rows/data in a base

## Workflow

### Step 1: Read and parse the `.base` file

Read the `.base` file. Identify:
- **Global filters** — which notes to include
- **Views** — each view's name, type, column order, view-specific filters, groupBy, limit
- **Formulas** — any computed columns (note: formulas cannot be fully evaluated without the Obsidian engine; show the formula expression instead or approximate where possible)

### Step 2: Find matching notes

Translate the global filters into file queries:

| Filter | How to find matching notes |
|--------|---------------------------|
| `file.folder == "X"` or `file.inFolder("X")` | `Glob("X/**/*.md")` |
| `file.hasTag("X")` | `Grep` for `tags:.*X` or `#X` in frontmatter |
| `file.ext == "md"` | Already covered by `.md` glob |
| `file.name` / `file.basename` comparisons | Filter glob results by name |
| Property comparisons (e.g., `status == "done"`) | Read frontmatter from candidate files and filter in post |

For compound filters:
- `and:` — intersect all conditions
- `or:` — union all conditions
- `not:` — exclude matching

Start with the most restrictive filter (usually folder) to minimize file reads.

### Step 3: Extract frontmatter from matching notes

For each matching note, read the YAML frontmatter (between `---` markers) to extract all properties referenced in the view's `order` list.

**Efficiency tips:**
- If there are many notes (>30), read files in parallel batches
- Only extract the properties needed by the views, plus any used in view-specific filters
- For `file.*` properties, derive from the file itself:
  - `file.name` — filename with extension
  - `file.basename` — filename without extension
  - `file.path` — path from vault root
  - `file.folder` — parent folder
  - `file.ext` — extension

### Step 4: Apply view-specific filters

Each view may have additional filters beyond the global ones. Apply these to narrow the note set for that specific view.

If a view has `limit: N`, only show the first N results.

If a view has `groupBy`, sort and group the results by that property.

### Step 5: Render as markdown table

For each view, output:

```
### View Name (view type)

| Column 1 | Column 2 | ... |
|----------|----------|-----|
| value    | value    | ... |
```

Column headers come from the view's `order` list. Use property display names from the `properties` section if defined, otherwise use the raw property name formatted as Title Case.

**Column rendering rules:**
- `file.name` / `file.basename` — render as `[[wikilink]]`
- List/array values — join with `, `
- Empty/missing values — show as empty cell
- `formula.*` — show as `(formula: expression)` since formulas can't be fully evaluated outside Obsidian. For simple arithmetic or string formulas, attempt to compute the value.
- Dates — format as `YYYY-MM-DD`

### Step 6: Summary

After rendering all views, briefly note:
- Total number of notes matching the global filter
- Any formulas that couldn't be evaluated
- Any filters that couldn't be fully applied

## Example output

Given a base filtering `file.folder == "Files/Places"` with a table view ordering `[file.name, type, status, rating, location]`:

### Table (table)

| Name | Type | Status | Rating | Location |
|------|------|--------|--------|----------|
| [[Adriatico's]] | Pizza; Sicilian; Casual | Not Visited | | 113 W McMillan St, Cincinnati, OH 45219 |
| [[Agave & Rye]] | Tacos, Mexican, Fusion | Visited | | 3825 Edwards Rd, Cincinnati, OH 45209 |
| ... | ... | ... | ... | ... |

## Limitations

- **Formulas**: Cannot fully evaluate Obsidian formula expressions (they depend on the Obsidian runtime). Simple math and string operations can be approximated.
- **Sorting**: Base views in Obsidian may have interactive sorting state not captured in the `.base` file. Default to the file system order unless `groupBy` or explicit sort is specified.
- **Large vaults**: For folders with hundreds of notes, consider showing a summary or asking the user which view/subset to render.
