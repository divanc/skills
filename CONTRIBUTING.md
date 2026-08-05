# Contributing

## Layout

```
.claude-plugin/
  plugin.json       # plugin manifest, lists every shipped skill
  marketplace.json  # makes this repo its own marketplace
skills/
  <name>/SKILL.md   # one directory per skill
```

Every new skill needs its path added to `skills` in `plugin.json`.

## Local development

Load the plugin straight from the working copy, no install:

```bash
claude --plugin-dir .
```

After editing a skill, run `/reload-plugins` in the session to pick up changes.
