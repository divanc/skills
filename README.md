# divan/skills

My agent skills, packaged as a Claude Code plugin. Small, composable, hackable.

## Install

Add the marketplace, then install the plugin:

```
/plugin marketplace add divanc/skills
/plugin install divan@skills
```

Skills are then invoked namespaced, e.g. `/divan:devibe`.

## Local development

Skills in this repo can be used directly without installing:

```bash
ln -s "$PWD/skills/<name>" ~/.claude/skills/<name>
```

## Layout

```
.claude-plugin/
  plugin.json       # plugin manifest, lists every shipped skill
  marketplace.json  # makes this repo its own marketplace
skills/
  <name>/SKILL.md   # one directory per skill
```

Every new skill needs its path added to `skills` in `plugin.json`.

## License

MIT
