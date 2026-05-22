---
name: lead-delegation
description: "Use when an agent that has subordinates (the orchestrator/team-lead, or any LEAD like qa-lead/backend-lead/frontend-lead) received work and must split it across its agents instead of doing it alone. Triggers: receiving a task batch, being about to execute work yourself while subordinates sit idle, having idle workers. Enforces decompose→assign→review, never execute. NOT for workers (devs/testers) — they execute directly."
---

# Lead Delegation

If you have agents reporting to you, you do NOT execute the work — you **decompose, assign, review, consolidate**. Your subordinates execute. If you catch yourself opening files to fix them, running the test browser, or writing code while a subordinate sits idle — STOP. That is their job. Your value is parallelism: 2-3 agents in flight at once beats you doing it serially.

## Who this is for (the hierarchy)

Same loop applies at every level — only the names change:

| You are | Your subordinates | You delegate | You do NOT |
|---|---|---|---|
| orchestrator (team-lead) | leads (qa/backend/frontend) | task batches per domain | implement, test, review code yourself |
| lead (qa/backend/frontend) | devs / testers | one task per worker | run agent-browser / pytest / edit files |
| worker (dev / tester) | — none — | nothing — you EXECUTE | (this skill does not apply to you) |

Rule of thumb: if someone reports to you and is idle, the work is theirs, not yours. The orchestrator delegating to leads, and a lead delegating to workers, are the same move one level apart.

## The one rule

> If a worker exists who can do this task, the lead must NOT do it. The lead assigns it and waits.

You execute directly ONLY when: zero idle workers AND the task is blocking everything else AND it is a 1-line trivial check. Otherwise: delegate.

## The delegation loop

```
1. RECEIVE batch from orchestrator (team-lead)
2. DECOMPOSE into worker-sized tasks (one task = one worker, one clear deliverable)
3. CREATE each as a TaskCreate task
4. ASSIGN: TaskUpdate(task_id, owner="<worker-name>") — round-robin across your workers
5. NOTIFY each worker: SendMessage(to=worker, "you own task #N: <what + how to verify>")
6. WAIT — go idle. Workers report back automatically when done.
7. REVIEW each worker's report. Reject + reassign if incomplete.
8. CONSOLIDATE all worker results into ONE report. SendMessage to team-lead.
```

## Concrete: splitting work across workers

You have 5 pages to QA, 2 testers. Do NOT test page 1 yourself while testers idle.

```
TaskCreate "QA /leaderboard"  → TaskUpdate owner=tester-1
TaskCreate "QA /trends"       → TaskUpdate owner=tester-1
TaskCreate "QA /tasks"        → TaskUpdate owner=tester-1
TaskCreate "QA /trajectories" → TaskUpdate owner=tester-2
TaskCreate "QA /settings"     → TaskUpdate owner=tester-2
```
Then SendMessage each tester their list with the exact workflow + acceptance check. Then go idle. They run in parallel; you wait.

## Worker brief template

When assigning, give the worker everything to act WITHOUT coming back to ask:

```
You own task #<id>: <one-sentence goal>.
Steps: <exact commands or files>.
Done when: <concrete, checkable acceptance criterion>.
Report back: <what facts I need in your reply>.
```

Vague brief → worker stalls or guesses. Specific brief → worker finishes unattended.

## Review gate (don't rubber-stamp)

A worker says "done." Before you mark the task complete:
- Did they report the ACTUAL acceptance criterion result, or just "looks fine"?
- For code: did they paste the test/lint/build exit status?
- For QA: did they give per-item status, not a vague "all good"?

If the report is thin → SendMessage worker: "reopen, give me <specific missing fact>." Do NOT fill the gap yourself.

## Consolidate up

The orchestrator wants ONE report, not N forwarded messages. Fold worker results into a table:

```
<item> | <status> | <issue / evidence>
```

Then one SendMessage to team-lead. That is the lead's deliverable.

## Anti-patterns (stop if you do these)

- ❌ Lead runs `agent-browser` / `pytest` / edits a file while workers sit idle.
- ❌ Lead "just does the first one to show how" — workers learn from the brief, not your demo.
- ❌ Lead forwards raw worker messages without consolidating.
- ❌ Lead marks a task done on a one-word "done" with no evidence.
- ❌ Lead asks orchestrator a question a worker could answer — route it to the worker.

## When you genuinely have no workers

Then say so to the orchestrator: "no idle workers, I will execute directly" — and only then do the work yourself. Silence + self-execution is the failure mode this skill exists to prevent.
