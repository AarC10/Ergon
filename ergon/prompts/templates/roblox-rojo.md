# Roblox / Rojo task brief

## Goal

(What does the player experience after this ships?)

## Place / project context

- Game name:
- Rojo project file:
- Affected services: (ServerScriptService, ReplicatedStorage, StarterPlayer, ...)
- Affected gameplay systems:

## Acceptance criteria

- [ ] `rojo build -o build.rbxlx` succeeds.
- [ ] (in-place play test step — what the human will look for)
- [ ] Server stays authoritative for any new behaviour involving trust.

## Constraints

- Do not add paid third-party assets.
- Preserve existing Rojo project layout.
- Server authoritative for damage / state changes.
- Keep replication payload reasonable.
- (project-specific: combat rules, anti-exploit, etc.)

## Validation

- rojo build -o build.rbxlx
- (optional: a luau-language linter / type check command)

## Notes / references

- Related modules:
- Prior decisions: `.ergon/memory/decisions.md`
