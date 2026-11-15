# Idea: a campaign from one brief

Status: **ideas only, nothing decided.** Brainstormed on 2026-11-15. This note records the idea so
it isn't lost; a real design comes later.

## Why

- Folio is a portfolio project, shown to recruiters and hiring managers next to Open Door,
  Packwright, and ResumeIQ.
- The test for any agent framework: the feature has to need at least one of these. Folio's current
  features don't. (DECISIONS #8 rejected full LangChain for a related reason: the retrieval
  pipeline is four simple steps, so calling the SDKs directly is lighter.)
  - pausing to wait for a person, then resuming
  - loops, where a step sends work back
  - parallel branches that get merged
  - several agents with different jobs
- This feature needs all four, and it's a real job for Folio's users: a marketer launching
  something needs several pieces that agree with each other, not one post.
- It would show multi-agent work, which ResumeIQ's planned LangGraph upgrade (one fact-checking
  agent) doesn't really cover.

## What Folio already has

The "LinkedIn Post" mode is a small, fixed version of this: one brief, one retrieval, a streamed
caption, then a matching card distilled from it. There are also separate generators for text posts,
image cards, and documents, and each records which brand chunks it used. (Template fills work
differently: they fill placeholders in an uploaded file rather than writing from a brief, so they
may not fit a campaign.)

## The idea

A text sketch, not a design:

```
Brief: "Launch Verdure's recycled-cork wall panels in March"

1. The plan                                      waiting for you
   - LinkedIn post + photo card    angle: where the cork comes from
   - Statement card                angle: the key product number
   - One-pager (PDF)               angle: specs for architects
   [Edit plan]  [Approve]

2. Writing (all three at once)
   - LinkedIn post + card   on-brand 8.6
   - Statement card         on-brand 5.9, sent back: "too salesy"
   - One-pager              on-brand 8.1

3. Review the set
   All pieces agree on the product name, launch date and claims.
   [Open each]  [Regenerate one]
```

1. **A planning agent** reads the brief and the brand material and proposes a short set of pieces,
   each with its own angle.
2. **The workflow pauses** for the person to edit or approve the plan.
3. **Each piece is written in parallel** by the generators Folio already has.
4. **A brand-voice reviewer agent** scores each piece against a rubric and sends weak ones back with
   a reason, at most once or twice.
5. **A final check across the set** confirms the pieces agree: the same product name, dates,
   numbers, and claims. A piece that disagrees goes back for a rewrite (within the same cap), and
   regenerating one piece later reruns the check. No single generation can do this today, and it's
   the real new value.

## Why a framework is justified here

| Need in this feature | What a framework like LangGraph gives you |
|---|---|
| The plan waits for a person, maybe for hours | The run's state is saved and resumed (a MongoDB storage package exists) |
| Pieces written at the same time | Built-in fan-out and merge |
| The reviewer sends a piece back | A loop with a retry cap |
| Planner, writers, and reviewer | Separate agents with clear handoffs |
| The person watches it happen | Streams each step, which fits Folio's existing streaming |

## Reused and new

- **Reused:** retrieval, the existing generators (called directly inside the server, not through
  their HTTP routes), streaming, card rendering, document export, generation history.
- **New:** a campaign record linking its pieces, the planner's prompt and plan format, the reviewer's
  brand-voice rubric, the graph, one campaign screen, and evals.

## How to prove it works

- **A brand-voice judge**, checked against a set of independent grades before it's trusted. Open
  Door did this with separate Claude Opus graders and got about 91% agreement.
- **A consistency check** that facts match across the pieces.
- **Before and after:** the same briefs generated one piece at a time versus as a campaign, scored by
  both checks.

## Guards against over-engineering

- **Small and fixed:** at most four pieces, at most two rewrites per piece.
- **The person stays in charge:** they approve the plan and the result. No publishing or scheduling
  to LinkedIn.
- **Demo cost:** a typical campaign is maybe 8 to 12 model calls instead of 1 or 2. With every
  guard maxed out (four pieces, two rewrites each, a review on every attempt) it's closer to 38.
  Today's demo quota counts one unit per paid request (DECISIONS #35) and the generate routes
  have a per-minute rate limit, so both need a decision; see the open questions.

## The video moment

The plan appears and waits for approval, three pieces write at once, and one is visibly sent back
with "too salesy." It reads with the sound off.

## Open questions

- **Framework:** LangGraph (the most requested in job postings; shows a different pattern from
  ResumeIQ's) or Strands Agents (AWS-native).
- **Retrieval:** one search for the whole campaign, or one per piece's angle.
- **Reviewer:** judges each piece alone, or the whole set together. The scores in the sketch are
  placeholders: the scale and the pass mark that triggers a rewrite still need defining.
- **Demo quota:** what a campaign costs against the daily demo limit (one unit, one per model call,
  or something in between), keeping in mind DECISIONS #35 rejected a cost-weighted budget.
