# 10 — Workflow Builder

A visual, no-code automation canvas for approval routing — inspired by **ClickUp Automations + Monday.com + Zapier**, but purpose-built for contract approvals (sequential, parallel, conditional, escalating). A non-engineer (legal ops, an admin) builds and runs it; the system executes it deterministically and audibly.

---

## 1. Concepts

- **Workflow (definition):** a named, versioned graph of nodes + edges. Has a status (`draft` / `active` / `archived`), can be set as the **default** for one or more contract types, and is owned/edited by Manager+ roles.
- **Run (instance):** created when a contract enters a workflow ("Submit for approval"). Carries the contract's data (type, value, department, owner, risk, tags, custom fields) so condition nodes can branch on it. Tracks current node(s), history, timers, decisions.
- **Node types:**
  - **Start** — the entry; every workflow has exactly one.
  - **Approval step** — one or more approvers must act (configurable: *all* must approve / *any N* / *first to respond*); decisions allowed (approve / reject / request changes / abstain — configurable); each approver gets a notification + an inbox item; produces an audit entry per action.
  - **Parallel group** — fans out to multiple branches that all run simultaneously; rejoins (with a join rule: all branches complete / first branch completes / N branches).
  - **Condition (branch)** — evaluates an expression over the contract's data (`value > 100000`, `department == "Procurement"`, `risk in ["high","critical"]`, `tags contains "government"`, `custom.cost_center == "X"`, `counterparty.is_new == true`, AND/OR/NOT, nested) → routes to the matching outgoing edge (with a default/else edge).
  - **Notify** — send a notification (to a user / role / team / the owner / a webhook / Slack-Teams) without pausing — "FYI legal that a high-value deal is in flight."
  - **Set field / tag** — mutate the contract (add a tag, set a custom field, set a flag) as the run progresses ("mark `legal-reviewed = true`").
  - **Wait / SLA timer** — a step has an SLA (e.g., "approve within 2 business days", honoring the tenant's calendar/holidays); on approaching → reminder(s); on breach → an **escalation action** (remind harder / escalate to a named user or the approver's manager / skip this step / auto-approve / route to a different branch).
  - **Sign step** — once approvals pass, hand off to the signature flow (the workflow can model "approve → then sign → then notify finance"); the run completes when signing completes.
  - **Sub-workflow** — call another workflow (composition; e.g., a shared "Legal review" sub-workflow used by many top-level workflows).
  - **End** — terminal; the run finishes; the contract advances (to `approved` → `out_for_signature` → … per what came before).
- **Roles in a step resolve dynamically:** "specific user(s)", "any user with role X", "the contract owner", "the contract owner's manager", "the head of department {from a field}", "the user named in custom field {legal_lead}", "the last person who edited the contract", "a round-robin among team Y". Resolution happens at run time; if it resolves to nobody → the run pauses with an "unassigned step — admin attention needed" alert.

---

## 2. The builder UI

```
┌── node palette ──┐┌────────────────────── CANVAS ─────────────────────┐┌── inspector ──┐
│ + Approval step  ││  ┌─────┐                                          ││ Approval step  │
│ + Parallel group ││  │Start│                                          ││ "Manager OK"   │
│ + Condition      ││  └──┬──┘                                          ││ Approvers:     │
│ + Notify         ││     ▼                                             ││  ◉ Owner's mgr │
│ + Set field/tag  ││  ┌──────────────┐                                 ││  ○ Role: Mgr   │
│ + Wait / SLA     ││  │ Approval:    │  ←── selected (blue outline)     ││  ○ User(s)…    │
│ + Sign step      ││  │ Manager OK   │                                 ││ Rule: all ▾    │
│ + Sub-workflow   ││  └──────┬───────┘                                 ││ Decisions:     │
│ + End            ││         ▼                                         ││  ☑ approve     │
│ ──────────────── ││  ┌────────────────────┐  yes  ┌───────────────┐   ││  ☑ request chg │
│ Templates:       ││  │ Condition:         ├──────▶│ Parallel:     │   ││  ☑ reject      │
│  • Standard      ││  │ value > $100,000?  │       │  Legal │ CFO   │   ││ SLA: 2 biz-days│
│  • High-value    ││  └────────┬───────────┘       └──────┬────────┘   ││ Remind @ 1d    │
│  • Government    ││           │ no                       ▼ (join: all)││ On breach:     │
│  • Procurement   ││           ▼                  ┌───────────────┐    ││  ◉ escalate→VP │
│                  ││     ┌──────────┐             │ Sign step     │    ││  ○ auto-approve│
│ [Import] [Export]││     │   End    │◀────────────┤  then → End   │    ││  ○ skip step   │
│                  ││     └──────────┘             └───────────────┘    ││ [delete node]  │
│                  ││  [+ zoom][fit][minimap][↶ undo][↷ redo]           ││                │
└──────────────────┘└────────────────────────────────────────────────────┘└────────────────┘
 Top bar: [Workflow name]  Status: ●Draft → [Activate]  · Default for: [MSA, SLA ▾]  · [Simulate ▾]  · Versions ▾
```

- **Palette** (left): drag a node onto the canvas; a set of **starter templates** (Standard 1-step, High-value 3-step, Government, Procurement, HR-onboarding, Legal-review sub-workflow) to clone-and-tweak.
- **Canvas** (center): pan/zoom, minimap, snap-to-grid, auto-layout option, drag to connect nodes (edges show labels on condition branches — "yes"/"no"/value labels), multi-select + align, undo/redo, copy/paste nodes; nodes show a status icon (config-complete / incomplete / has-warning); a "lint" panel lists problems.
- **Inspector** (right): the selected node's full config (approvers + resolution, rules, allowed decisions, SLA + reminders + on-breach action, the condition expression with a friendly builder *and* a raw-expression mode for power users, notify recipients/channels, field mutations, sub-workflow selection).
- **Top bar:** name, status toggle (draft → active; you can't activate an invalid workflow), "default for {contract types}", **Simulate** (pick a sample contract or enter sample values → the canvas animates the path the run would take, showing which branch each condition picks, who each step resolves to, where SLAs would fire — so you can verify before activating), version history (every activation is a version; in-flight runs keep the version they started on; "diff versions").
- **Validation (must pass to activate):** exactly one Start; every path reaches an End; no orphan nodes; no infinite loops (cycles only allowed via explicit "send back to author then resubmit" which re-enters the run, not loops the graph); every Approval step has a resolvable assignee config; every Condition has a default/else edge; every Parallel group has a join rule; every SLA has an on-breach action.

---

## 3. The run experience (recap of Module 12's run views)

- **On a contract:** the **Approvals tab** shows the run as a vertical timeline — each node with its status (done / current / pending / skipped), who acted, when, the decision, the comment, and the duration; the current blocker is highlighted ("waiting on Legal — 2 days, SLA in 4h"); inline actions if it's *you* (approve / request changes / reject + comment); owner/admin actions (remind, reassign/delegate, escalate now, skip step (audited), change workflow (audited)).
- **Per workflow** (`/workflows/:id/runs`): a list of all runs (which contract, current node, time-in-stage, status), plus aggregate analytics — **bottleneck heatmap** (node × week, colored by avg time-in-node), avg time per node, SLA-breach rate per node, rejection rate, escalation count, "which approver is slowest"; this feeds the dashboard's "Workflow Health" widget and the Reports → Workflow page.
- **For an approver:** the **My Approvals** inbox (Module 20) — each card shows the contract + the AI summary + risk flags + who else is on the chain + time waiting + inline Approve / Request changes / Reject; "open the contract" is one click; approve-from-email and approve-from-mobile are 2-tap; "delegate my approvals to X until {date}" reroutes + notifies + audits.

---

## 4. Edge cases & rules

- **Sent back to author** ("request changes") → the run pauses, the contract goes to `changes_requested`, the author edits and resubmits → the run resumes from the step that sent it back (configurable: resume there / restart the whole workflow).
- **Reject** → terminal; contract → `rejected`; the run ends; the author is notified with the reason; they can revise and start a new run.
- **Approver leaves / is deactivated** while a run waits on them → the step re-resolves (or pauses with an "unassigned" alert for an admin to reassign).
- **Workflow edited while runs are in flight** → in-flight runs keep their version; new runs get the new version; "migrate in-flight runs to v2?" is offered but defaults to no.
- **The contract's data changes mid-run** (e.g., value edited above the high-value threshold) → conditions are evaluated when the run *reaches* them, so a later condition sees the new value; already-passed steps aren't re-run; a warning is shown if a change would have changed an earlier branch ("value is now $150k — this was routed as a sub-$100k deal; restart?").
- **Parallel branch one rejects** → configurable: reject the whole run / continue other branches and let the join rule decide / pause for an admin.
- **SLA on a weekend/holiday** → SLAs use the tenant's business calendar (configurable holidays, working hours); "2 business days" skips them.
- **Out-of-office** → delegation reroutes; un-delegated → reminders + eventual escalation per the step's on-breach action.
- **Conditions reference a field that's empty** → the expression treats it as null; the default/else edge catches it; a lint warning at design time ("this condition reads `custom.cost_center` — what if it's blank?").
- **No workflow configured for a contract type** → "Submit for approval" prompts: pick a workflow / use the org default / "no approval needed — go straight to signature" (if the user's role allows skipping approval).
- Everything — every node entered, every decision, every reminder, every escalation, every reassignment, every skip, every workflow change — is in the **audit log**.

---

## 5. Data model (see Doc 15 for full schema)

`workflow_definitions` (id, tenant_id, name, status, default_for_types[], current_version) · `workflow_versions` (id, definition_id, version, graph JSONB {nodes[], edges[]}, created_by, created_at) · `workflow_runs` (id, tenant_id, contract_id, definition_id, version, status, started_at, completed_at, current_node_ids[], context JSONB) · `workflow_run_steps` (id, run_id, node_id, node_type, status, assignees JSONB resolved, decision, decided_by, decided_at, comment, sla_due_at, sla_breached_at, escalated_to) · `workflow_run_events` (id, run_id, event, payload, at) — the run timeline. The engine is a deterministic state machine: on each event (decision, timer fire, contract change) it advances the run, resolves the next node(s), creates step records, sends notifications, mutates the contract, emits domain events; timers are Celery `eta`/`countdown` tasks (or a beat scan) keyed to `sla_due_at`; everything is idempotent and tenant-scoped.

**RTL/Mobile:** the canvas mirrors (flow reads right-to-left in RTL; edges and arrows flip); the canvas is a desktop-class authoring tool — on mobile you can *view* a workflow and *act on* runs (approve/reject from the inbox) but not edit the graph. See Doc 12.
