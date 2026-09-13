# V1 UI compatibility contract

The first production bot UI is the operator-facing UX baseline for V2.

V2 may add state, safety evidence, ownership modes, battery identity and new workflows,
but it must not replace the familiar primary dashboard/navigation without a safety
reason. Presentation compatibility does **not** restore V1 actuator authority.

## Canonical primary shell

The main graph/dashboard keeps the familiar V1 hierarchy:

1. graph range: `30m / 2h / Session`;
2. `Refresh / Full info`;
3. `Logs / AI analysis`;
4. when a new program is positively allowed: `START / Modes`.

V2 may append an `More` entry for additive controller/service functions.

The graph row is supplied by `operator_dashboard`; the remaining shell is composed by
`v1_ui_compat` around the semantic `operator_hmi` keyboard.

## Semantic substitutions

The visible V1 concepts are retained while their callbacks use V2 authority:

| V1 concept | V2 production callback / meaning |
| --- | --- |
| Refresh | `operator_refresh` — read-only semantic panel refresh |
| Full info | `operator_details` — truthful semantic details |
| Logs | `logs` |
| AI analysis | `ai_analysis` |
| START | `v2_batteries` — enter the V2 battery/program chooser; never raw Output ON |
| Modes | `charge_modes` — V2 program/mode chooser |
| STOP | existing composed managed Stop transaction; never a newly introduced raw OFF path |
| 30m / 2h / Session | `operator_graph_*` through the graph dashboard |
| More | `operator_more` — additive V2/service navigation |

## Safety precedence

V1 compatibility is a presentation layer only. The following always override visual
parity:

- unknown/stale Output is not OFF;
- containment is never a START surface;
- active managed sessions keep the V2 pause/verified Stop transaction;
- HANDS_OFF and AUTONOMOUS keep their ownership-specific controls;
- adopted/interrupted Mix keeps its dedicated recovery/stop controls;
- terminal Storage does not regain Start/Stop merely for visual parity;
- final Output-truth and AUTONOMOUS filters run after the V1 shell and may remove
  controls whose physical preconditions are not positively proven.

This gives the project one stable operator UX while preserving the V2 authority model:

```text
V2 semantic state / evidence / authority
                 |
                 v
          operator_hmi
                 |
                 v
       V1-compatible shell
                 |
                 v
        Output-truth filter
                 |
                 v
       AUTONOMOUS filter
                 |
                 v
         Telegram operator
```
