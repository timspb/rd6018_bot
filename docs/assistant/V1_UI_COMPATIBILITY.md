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

V2 may append a `More` entry for additive controller/service functions.

The graph row is supplied by `operator_dashboard`; the remaining shell is composed by
`v1_ui_compat` around the **final permitted** semantic keyboard. The compatibility
adapter deliberately does not wrap the legacy
`app._build_dashboard_keyboard(is_on: bool, ...)` surface because that boolean cannot
distinguish confirmed OFF from stale/UNKNOWN Output.

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
- the shell may restore `START / Modes` only when the final V2 keyboard still exposes
  **both** safe IDLE entry callbacks (`v2_batteries` and `charge_modes`).

The installer is registered before Output-truth/AUTONOMOUS composition, but the graph
wrapper performs a dynamic call to `operator_hmi.build_operator_keyboard` at render
time. Therefore the effective production order is:

```text
fresh live telemetry
        |
        v
semantic/truthful HMI state
        |
        v
V2 ownership + Output-truth + AUTONOMOUS keyboard filters
        |
        v
final permitted callback set
        |
        v
V1-compatible graph/dashboard shell
        |
        v
Telegram operator
```

This ordering is intentional. The V1 layer consumes authority decisions; it does not
create them. If V2 removes either IDLE entry callback because Output is UNKNOWN,
ownership is unresolved, or AUTONOMOUS is active, the V1 shell treats the presentation
as containment and cannot reconstruct START, Modes or the additive `More` surface.
