# Assistant Documentation Index

This directory is the durable project memory for charge-strategy/controller work.

Do **not** reconstruct behavior from chat history when these documents answer the question.

## Source-of-truth order

When documents appear to disagree, use this order:

1. **`V2_DECISION_LOG.md`** — explicit accepted/rejected design decisions;
2. **`V2_OPEN_QUESTIONS.md`** — intentionally unresolved items; do not invent an answer;
3. **`CHARGE_STRATEGY.md`** — concise current production V2 strategy;
4. **`PB_RECOVERY_V2.md`** — V2 architecture/implementation overview;
5. **`V1_BEHAVIORAL_AUDIT.md`** — factual V1 baseline and hidden legacy contracts;
6. **`HISTORY.md`** — historical notes only; may be older than the documents above.

Executable tests and current code must agree with accepted decisions. If they do not, treat that as a bug/documentation drift to investigate, not permission to silently choose whichever version is convenient.

## What each file is for

### `V1_BEHAVIORAL_AUDIT.md`

A reconstruction of V1 on audited `main` commit `8d3e2af9c2f16721f3303579f12d4f39bcc98a13`.

Use it to answer:

- what did V1 actually do?
- which behavior was chemistry strategy vs implementation accident?
- which contracts live outside `charge_logic.py`?
- what must V2 preserve or explicitly supersede?

Do not edit V1 facts to make them look like V2.

### `V2_DECISION_LOG.md`

Numbered decisions (`D001`, `D002`, ...), including implementation status.

Use it to answer:

- what did we decide after reviewing V1?
- what was explicitly rejected?
- is a behavior already implemented or only accepted?

Every strategy change should add/update a numbered decision.

### `V2_OPEN_QUESTIONS.md`

Numbered unresolved questions (`Q001`, `Q002`, ...).

If a question is here, do not fill the gap from memory or generic battery theory. Resolve it explicitly, then move the result into `V2_DECISION_LOG.md`.

### `CHARGE_STRATEGY.md`

Short operational reference for the current production V2 controller.

It should remain readable enough to review before changing FSM/evidence logic.

### `PB_RECOVERY_V2.md`

Architecture and rollout description: domain model, authority boundaries, telemetry/evidence stack, safety path and rollback.

### `HISTORY.md`

Historical breadcrumbs. It is not the highest-authority document and may contain values that were later changed.

## Update protocol

For a behavior-changing controller commit:

1. identify whether it changes a V1-compatible contract or resolves a V2 open question;
2. update/add a `Dxxx` decision;
3. remove/update the corresponding `Qxxx` if resolved;
4. update `CHARGE_STRATEGY.md` if operator-visible strategy changes;
5. update `PB_RECOVERY_V2.md` if architecture/authority changes;
6. add deterministic tests;
7. keep factual V1 history unchanged unless the audit itself was factually wrong.

## Important terminology

Use these consistently:

- **battery voltage** — battery-side measurement used for chemistry decisions;
- **output voltage** — RD6018 output measurement, also relevant to hardware watchdogs;
- **temp_ext** — battery/external-probe temperature;
- **temp_int** — RD6018/controller/PSU temperature;
- **commanded setpoint** — software request;
- **configured/readback setpoint** — value confirmed from RD6018/HA telemetry;
- **measured value** — physical output/battery telemetry;
- **CV** — voltage controlled, current response (`Imin -> ΔI` evidence);
- **CC** — current controlled, voltage response (`Vmax -> ΔV` evidence);
- **recovery attempt** — intermediate bounded high-voltage service attempt inside Main/recovery loop;
- **Mix** — final recovery/mixing stage, distinct from intermediate recovery;
- **SAFE_WAIT** — output-OFF relaxation bridge with an early threshold and maximum wait;
- **Done/Storage** — normal program complete with managed float/storage output ON;
- **hard stop/fault** — de-energized safety state; not synonymous with Done.

## Rule for future assistants

If a proposed change contradicts an accepted decision, do not implement it just because the current code makes it easy. First surface the contradiction and update the decision log only after an explicit strategy decision.
