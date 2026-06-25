# Skills registry

Named, reusable run templates live in `skills.yaml` at the repo root. Each skill supplies defaults for a browser-agent run so you do not have to retype common queries and URLs.

## YAML format

`skills.yaml` is a mapping of skill names to configuration objects:

```yaml
skill_name:
  query: "Required natural-language task for the agent."
  description: "Optional one-line summary shown by --list-skills."
  initial_url: "https://example.com"   # optional
  concise_mode: true                   # optional bool
  model: "gemini-3.5-flash"            # optional
```

### Template variable `{url}`

Skills may include `{url}` in `query` and/or `initial_url`. Pass the value with `--skill-arg` on the CLI:

```bash
python main.py --skill price_check --skill-arg "https://shop.example.com/item"
```

Only `{url}` is supported — there is no general templating engine.

## CLI usage

| Flag | Purpose |
|------|---------|
| `--skill <name>` | Load defaults from `skills.yaml` |
| `--skill-arg <value>` | Fill `{url}` in the selected skill |
| `--list-skills` | Print skill names and descriptions, then exit |

Explicit flags override skill defaults when both are present:

```bash
python main.py --skill competitor_scan --query "Custom override query"
```

## Seed skills

### `repo_summary`

Summarize how the main functions in a GitHub file work, using the file's raw contents.

```bash
python main.py --skill repo_summary \
  --skill-arg "https://github.com/google/computer-use-preview/blob/main/agent.py"
```

GitHub blob URLs are rewritten to `raw.githubusercontent.com` for `initial_url`.

### `competitor_scan`

List today's top five Product Hunt launches.

```bash
python main.py --skill competitor_scan
```

### `price_check`

Extract the current price and availability from a product page.

```bash
python main.py --skill price_check --skill-arg "https://www.example.com/product/123"
```
