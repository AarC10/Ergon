# Zephyr / embedded task brief

## Goal

(What does the firmware need to do? Which board and which subsystem?)

## Hardware context

- Board:
- MCU:
- Peripherals involved:
- Pin / DT overlay implications:

## Acceptance criteria

- [ ] Builds for `<board>` with `west build -b <board> app`.
- [ ] Passes `west twister -T tests` (or the relevant subset).
- [ ] (behavioural check on hardware, if applicable — describe the test rig)

## Constraints

- No blocking calls in ISR context.
- Keep stack/heap usage within budget X.
- Do not regress flash/RAM footprint without justification.
- (project-specific: real-time deadlines, safety levels, etc.)

## Validation

- west build -b <board> app
- west twister -T tests
- (optional: hardware-in-the-loop test command)

## Notes / references

- Datasheet sections:
- Related Zephyr samples:
- Prior incidents in `.ergon/memory/decisions.md`:
