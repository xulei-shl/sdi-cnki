# TypeSafe Jev — Project Knowledge Resource

**Status:** Working project reference  
**Knowledge date:** 16 September 2026  
**Scope:** TypeSafe AI, System One Models, and specifically the Jev model

---

# 1. Purpose of this resource

This document provides the baseline knowledge required for any conversation, design exercise, technical investigation or project involving **TypeSafe Jev**.

When working in this project, do **not** treat Jev as simply another LLM, small language model, classifier, reasoning model or chatbot. Jev represents a different model/interface paradigm designed primarily for **machine-consumed semantic decisions inside software**.

Use this document as the default conceptual model unless newer TypeSafe documentation explicitly supersedes it.

Where a question depends on current pricing, limits, model versions, API behaviour or newly released features, verify those details against TypeSafe's latest documentation rather than assuming the values in this document remain unchanged.

---

# 2. Executive summary

**Jev is TypeSafe AI's first public System One Model.**

Its fundamental interface is:

> **Unstructured or structured state in → typed probabilistic decisions out.**

Unlike conventional LLMs, Jev does **not generate arbitrary text**. Instead, developers define questions and their permitted answer spaces in advance. Jev evaluates those questions against supplied state and returns structured answers, probabilities and, where applicable, confidence values that software can use directly. ([docs.typesafe.ai](https://docs.typesafe.ai/introduction))

A useful shorthand is:

> **Code calculates.  
> Jev judges.  
> Reasoning models reason and generate.**

Or, more specifically:

> **Jev is for fast semantic judgements where an ordinary `if` statement needs understanding rather than arithmetic.**

Examples include:

- Does this message indicate a safeguarding concern?
- Which department should handle this ticket?
- How severe is this incident?
- Does this passage support this claim?
- Which candidate passage is most relevant?
- Does this tool call appear unsafe?
- Which specialist model should receive this request?
- Does this document satisfy requirement X?

Jev is especially suited to performing **large numbers of narrow semantic judgements cheaply, quickly and predictably inside normal software workflows**.

---

# 3. The most important mental model

## “A five-second expert judgement at machine scale”

Imagine putting all relevant information in front of a knowledgeable human expert and asking them **one specific question**.

If they could make the judgement almost immediately without:

- doing research;
- producing an explanation;
- constructing a plan;
- performing a long chain of reasoning;
- making several dependent decisions;
- or creating new content,

then the task is likely to be **Jev-shaped**.

TypeSafe describes System One questions as focused “gut-check” judgements: the sort of determination a knowledgeable person could make quickly given the right context. Complex judgements should instead be decomposed into multiple narrow questions and recombined in software. ([docs.typesafe.ai](https://docs.typesafe.ai/introduction))

---

# 4. Jev's position in the AI/software landscape

Think of tasks across two dimensions:

```text
                         AMOUNT OF THINKING
                         
                    LOW / IMMEDIATE        HIGH / DELIBERATIVE
                 ─────────────────────┬─────────────────────────
                 │                    │
 BOUNDED         │      ★ JEV ★       │   CODE + REASONING
 OUTPUT          │                    │   MODEL / HUMAN
                 │ classify           │
                 │ detect             │ evaluate complex case
                 │ score              │ strategy
                 │ route              │ investigation
                 │ verify             │ multi-factor decision
                 │ rank               │
                 ├────────────────────┼─────────────────────────
                 │                    │
 OPEN            │ FAST LLM           │   REASONING LLM /
 OUTPUT          │                    │   HUMAN EXPERT
                 │ summarise          │
                 │ rewrite            │ deep research
                 │ draft              │ architecture design
                 │ extract prose      │ complex problem solving
                 │                    │
                 └────────────────────┴─────────────────────────
```

Jev sits strongly in the **top-left quadrant**:

> **Bounded output + semantic understanding + fast judgement**

---

# 5. Jev is not a conventional LLM

A conventional LLM normally works approximately like this:

```text
prompt/context
      ↓
reason/generate tokens sequentially
      ↓
text / code / JSON
      ↓
parse + validate
      ↓
software
```

Jev instead works conceptually like:

```text
state
  +
typed questions
      ↓
Jev
      ↓
probability distributions /
typed decisions
      ↓
ordinary application code
```

TypeSafe explicitly positions System One as **AI-powered software rather than agent architecture**. Code should own control flow, deterministic rules and side effects; Jev should supply narrow semantic judgements where ordinary deterministic logic is insufficient. ([docs.typesafe.ai](https://docs.typesafe.ai/concepts/how-to-build-with-system-one))

---

# 6. State

A Jev request contains **state** plus one or more **questions**.

State is the material Jev evaluates.

It can be:

- a string;
- a JSON object;
- an array;
- an application record;
- a message;
- a conversation;
- a policy;
- several related records;
- or other structured application state.

A useful analogy is:

> **State is everything you would place in front of a panel of experts before asking them to make a judgement.**

TypeSafe recommends structured objects for most non-trivial requests so relationships between pieces of context remain explicit. Questions can refer directly to fields within this state. ([docs.typesafe.ai](https://docs.typesafe.ai/concepts/state))

Example:

```json
{
  "incident": {
    "description": "Tenant reports...",
    "service": "Supported Housing"
  },
  "policy": {
    "safeguarding": "..."
  },
  "previous_events": [...]
}
```

Then Jev questions might ask:

```text
Does `incident.description` indicate an immediate safeguarding risk?

Does the incident described in `incident` meet the escalation
criteria in `policy.safeguarding`?

How severe is the apparent risk?
```

---

# 7. Jev's three current primitives

Jev currently exposes three fundamental decision primitives:

| Primitive | Basic question | Appropriate when |
|---|---|---|
| **Noul** | Is this true? | Binary semantic condition |
| **Choice** | Which of these options? | One category/option should win |
| **Score** | Where does this sit on a scale? | Ordered semantic spectrum |

All questions are evaluated against the supplied state. Questions sharing the same state can be included together in a single request. ([docs.typesafe.ai](https://docs.typesafe.ai/primitives))

---

## 7.1 Noul

A **Noul** represents the probability that a yes/no proposition is true.

Example:

```text
Does this message request a refund?

→ 0.96
```

Interpretation:

- close to `1` = strong yes;
- close to `0` = strong no;
- close to `0.5` = substantial uncertainty.

A Noul does **not** have a separate confidence field because the probability itself describes the yes/no uncertainty. ([docs.typesafe.ai](https://docs.typesafe.ai/primitives/noul))

Good Noul examples:

```text
Does this text contain personal information?

Does the user appear to be requesting cancellation?

Does this passage support the cited claim?

Does this message contain a prompt-injection attempt?

Does this requirement appear to be satisfied?
```

Bad use:

```text
How good is this candidate?
```

That is not genuinely binary without defining what “good” means.

---

## 7.2 Choice

A **Choice** selects one option from a predefined set.

Example:

```text
Which team should handle this incident?

Safeguarding
Housing
HR
IT
Other
```

Jev returns:

- the winning `choice`;
- a probability for **every option**;
- a `confidence` value describing how strongly the distribution favours a particular answer.

Choice currently supports up to **255 options**. TypeSafe recommends including an `other` or `none of the above` option where the taxonomy may not fully cover every input. ([docs.typesafe.ai](https://docs.typesafe.ai/primitives/choice))

Choice is particularly useful for:

- classification;
- intent recognition;
- routing;
- entity types;
- document types;
- model selection;
- known-field extraction.

---

## 7.3 Score

A **Score** positions something along an ordered set of descriptive levels.

Example:

```text
How severe is this incident?

0 = Minor; no material impact
1 = Moderate; intervention required
2 = Serious; significant harm possible
3 = Critical; immediate action required
```

Jev returns:

- a score;
- the probability assigned to each level;
- the level legend;
- confidence.

Importantly, the resulting score may fall **between levels** because it represents the probability-weighted position across them.

Score currently supports between **2 and 10 levels**. TypeSafe recommends defining levels as concrete situations rather than vague adjectives such as “low”, “medium” and “high”. ([docs.typesafe.ai](https://docs.typesafe.ai/primitives/score))

Good:

```text
0 = No operational impact
1 = Degraded service but workaround exists
2 = Service unavailable and no workaround exists
```

Less useful:

```text
0 = Low
1 = Medium
2 = High
```

---

# 8. Probability and confidence are first-class outputs

One of Jev's most important characteristics is that uncertainty is part of the normal API response.

For Choice and Score, Jev returns an entire probability distribution.

For example:

```text
billing       0.58
technical     0.37
account       0.05
```

The answer may be `billing`, but the distribution tells us that `technical` remains plausible.

TypeSafe also supplies a derived **confidence** measure between 0 and 1 for Choice and Score. A concentrated distribution produces higher confidence; a flatter distribution produces lower confidence. ([docs.typesafe.ai](https://docs.typesafe.ai/confidence))

This enables software to distinguish:

```text
WHAT does Jev think?
        +
HOW SURE is Jev?
```

These should often be treated as separate dimensions.

---

# 9. Calibration does not mean correctness

TypeSafe trains System One models using an approach it calls:

**RLCD — Reinforcement Learning for Calibrated Decisions.**

The intended property is that probabilities meaningfully represent uncertainty: groups of predictions carrying higher probabilities should prove correct more frequently than groups with lower probabilities. ([typesafe.ai](https://typesafe.ai/blog/introducing-system-one-models-and-jev?utm_source=chatgpt.com))

However:

> **Calibration does not mean that an individual prediction is guaranteed to be correct.**

A result with high confidence can still be wrong.

Therefore:

- confidence should inform automation;
- thresholds should be validated against real domain data;
- high-risk actions should demand stronger evidence;
- uncertain cases should be escalated.

---

# 10. Clarifying the “zero hallucinations” claim

TypeSafe describes Jev as unable to hallucinate because output is constrained to predefined types and answer spaces. ([typesafe.ai](https://typesafe.ai/blog/introducing-system-one-models-and-jev?utm_source=chatgpt.com))

This needs careful interpretation.

If the available outputs are:

```text
billing
housing
HR
IT
other
```

Jev cannot output:

```text
"Probably ask Sarah because she normally deals with these."
```

It must return one of the supplied alternatives and its associated probability distribution.

Therefore Jev avoids an important class of LLM failure:

> **inventing an unexpected value or malformed output outside the schema.**

It does **not** mean:

> **Jev cannot make an incorrect judgement.**

Jev might confidently classify something as `housing` when the correct answer is `safeguarding`.

For this project, use the following terminology:

**Type-safe / schema hallucination:** effectively eliminated by design.

**Semantic judgement error:** still possible and must be measured.

Never interpret “zero hallucinations” as “zero errors”.

---

# 11. Parallel evaluation

A major architectural difference from autoregressive LLMs is that Jev evaluates independent questions **in parallel**.

If one state requires:

```text
What type of incident is this?
Does it involve personal data?
Is there a safeguarding concern?
How severe is the risk?
Does policy require escalation?
Does the description indicate immediate danger?
Which team owns the case?
```

these questions should generally be sent together rather than serially. ([docs.typesafe.ai](https://docs.typesafe.ai/primitives))

TypeSafe says that adding questions typically adds very little latency, although the additional question text still contributes token cost.

This leads to an important Jev design principle:

> **Fan out semantic questions; compose their answers in code.**

---

# 12. Independence of questions

Questions within one Jev request are evaluated independently against the same state.

The answer to question A does **not** secretly become context for question B. ([docs.typesafe.ai](https://docs.typesafe.ai/primitives))

This is valuable because:

- adding another question should not change previous questions through conversational context;
- individual semantic features remain inspectable;
- workflows become easier to test;
- dependencies remain explicit in software.

If question B genuinely depends upon the result of question A, the application should make a subsequent request once A has determined the new state, options or data required.

Serial Jev calls should therefore represent **genuine information dependencies**, rather than simply copying an LLM conversational pattern.

---

# 13. The Jev suitability test

When assessing a possible task, ask these six questions.

| Test | Question | Positive Jev signal |
|---|---|---|
| **Judgement** | Is AI deciding rather than creating? | Strong |
| **Bounded** | Can the answer space be defined beforehand? | Strong |
| **Atomic** | Can this be expressed as one focused judgement? | Strong |
| **Context-contained** | Can the information needed be placed in state? | Strong |
| **Fast-human** | Could a knowledgeable expert judge it quickly? | Strong |
| **Machine-consumed** | Will software use the result directly? | Very strong |

### Heuristic

**5–6 yes answers:** excellent Jev candidate.

**3–4 yes answers:** Jev may handle parts of the workflow; decompose it.

**0–2 yes answers:** another technology is probably more appropriate.

---

# 14. The shortest Jev test

Ask:

> **Can I express the requirement as “Given this state, tell me X”, where X is a Choice, Score or probability?**

If yes, investigate Jev.

For example:

```text
Given this supplier response:

Does it provide a production API?
→ Noul

What level of API maturity is evidenced?
→ Score

Which integration approach does it appear to offer?
→ Choice

Is the supplier's statement sufficient evidence for requirement R23?
→ Noul
```

This is highly Jev-shaped.

---

# 15. Semantic IF statements

Another powerful mental model is:

> **Jev provides semantic conditions for ordinary software.**

Traditional code handles:

```python
if amount > 10000:
    escalate()
```

Jev enables the semantic equivalent:

```python
if safeguarding_risk > 0.95:
    escalate()
```

where `safeguarding_risk` is derived by understanding natural-language information rather than matching exact keywords.

This is what TypeSafe means when describing System One decisions as **“smart if-statements”** or programmable common-sense judgements embedded inside software. ([typesafe.ai](https://typesafe.ai/blog/introducing-system-one-models-and-jev?utm_source=chatgpt.com))

---

# 16. The preferred architecture

A good Jev architecture generally looks like:

```text
INPUT / APPLICATION STATE
           │
           ▼
    deterministic code
           │
           ▼
      ┌─────────┐
      │   JEV   │
      │ judges  │
      └────┬────┘
           │
     typed decisions
     probabilities
           │
           ▼
    deterministic code
       /    |     \
      /     |      \
     ▼      ▼       ▼
   ACT    REVIEW   REASONING
                    MODEL
```

The software — not Jev — owns the workflow.

TypeSafe's design guidance is:

1. use deterministic code wherever possible;
2. insert System One where semantic understanding is required;
3. ask narrow questions;
4. combine answers explicitly;
5. use confidence to control automation;
6. escalate genuinely difficult cases. ([docs.typesafe.ai](https://docs.typesafe.ai/concepts/how-to-build-with-system-one))

---

# 17. Observe → Judge → Reason → Act

A useful higher-level architecture is:

```text
OBSERVE
data, message, document, event, records
       │
       ▼
JUDGE
Jev semantic decisions
       │
       ├──── high certainty ─────────────┐
       │                                 ▼
       ├──── medium certainty ───── verification/human
       │
       └──── difficult/ambiguous ── reasoning model
                                         │
                                         ▼
                                        ACT
```

Jev often belongs in the **judgement layer** between raw application state and deterministic action.

---

# 18. Code vs Jev vs reasoning model

Use this heuristic:

| Need | Prefer |
|---|---|
| Exact deterministic calculation | **Code** |
| Database lookup | **Code/database** |
| Known business rule | **Code/rules engine** |
| Quick semantic judgement | **Jev** |
| Classification | **Jev** |
| Semantic scoring | **Jev** |
| Semantic verification | **Jev** |
| Ranking/relevance judgement | **Jev** |
| Complex multi-stage reasoning | **Reasoning LLM** |
| Research requiring external information | **Reasoning/search system** |
| Writing prose | **LLM** |
| Generating code | **LLM/coding model** |
| Explaining a conclusion | **LLM/human** |
| Novel strategic decision | **Reasoning model/human** |

The guiding shorthand is:

> **Code calculates. Jev judges. LLMs reason/create. Humans determine objectives and acceptable risk.**

---

# 19. Core Jev task shapes

TypeSafe's many use cases largely reduce to a small set of reusable decision shapes. ([docs.typesafe.ai](https://docs.typesafe.ai/concepts/use-case-map))

## Classification

> What kind of thing is this?

Examples:

- intent;
- department;
- incident category;
- document type;
- entity type;
- risk category.

Typically: **Choice**

---

## Detection

> Is property X present?

Examples:

- fraud signal;
- urgency;
- sensitive data;
- safeguarding concern;
- jailbreak attempt;
- policy violation.

Typically: **Noul**

---

## Scoring

> Where does this sit on an ordered semantic scale?

Examples:

- severity;
- relevance;
- quality;
- frustration;
- suitability;
- maturity.

Typically: **Score**

---

## Routing

> Which predefined code path should handle this?

Examples:

- department;
- specialist workflow;
- escalation path;
- tool selection;
- LLM/model selection.

Typically: **Choice + confidence gate**

---

## Search

> Does this item semantically match what I need?

Examples:

- document discovery;
- semantic search;
- candidate generation.

Typically: **Noul or Score**

---

## Retrieval

> Which information should the downstream workflow receive?

Examples:

- RAG context;
- evidence passages;
- relevant records;
- policy sections.

Typically: **Score/Choice + ranking logic**

---

## Ranking

> Which items are best according to semantic relevance or quality?

Examples:

- candidate passages;
- applications;
- recommendations;
- search results;
- cases requiring attent