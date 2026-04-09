---
name: obsidian-vector-search
description: Semantic search over the user's Obsidian vault using vector embeddings. Use when the user asks to find, search, look up, or discover notes, topics, ideas, or anything from their knowledge base by meaning or concept rather than exact keywords.
---

# Obsidian Vector Search Skill

Semantically search the vault using the `vector` binary in this skill's directory.

The skill directory is shown as **Base directory** at the top of this skill load. All paths below are relative to it.

## Setup

**API key required:** `OPENROUTER_API_KEY` will be set in the environment

**Binary:** `$SKILL_DIR/vector`
**Database:** `$SKILL_DIR/vector.db` (auto-created on first index)
**Vault root:** `/user-files/notes`

## Workflow

### 1. Check if indexed

Check whether `vector.db` exists in the skill directory. If not, or if the user asks to reindex:

```bash
cd "$SKILL_DIR" && ./vector index --vault /user-files/notes
```

This is incremental — only changed/new files are re-embedded. Safe to run anytime.

### 2. Search

```bash
cd "$SKILL_DIR" && ./vector search "your query" --top 5
```

Output is JSON to stdout, progress/errors go to stderr:

```json
[
  {
    "path": "Notes/Cooking/Sourdough.md",
    "title": "Sourdough",
    "heading": "## Starter Maintenance",
    "score": 0.87,
    "snippet": "Feed the starter every 12 hours..."
  }
]
```

### 3. Interpret and respond

- Read the top results and their snippets
- If a result looks highly relevant (score > 0.75), open the full note with Read to get more context
- Summarize findings for the user, linking to notes with `[[wikilink]]` syntax
- If results look stale or miss something obvious, suggest reindexing

## Tips

- Use `--top 10` for broader searches, `--top 3` for focused ones
- The score is cosine similarity (0–1); above 0.7 is generally a good match
- Chunking respects headings, so `heading` in results points to the relevant section
- Skips `.obsidian`, `.trash`, `.claude`, `.git` directories automatically
- `path` in results is relative to the vault root
