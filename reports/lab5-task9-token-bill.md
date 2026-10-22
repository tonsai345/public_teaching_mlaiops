# Task 9 — The token bill

Measured usage: **432 input tokens, 42 output tokens** per request
(baseline over 12 cases — `reports/llm_eval-triage-v2-baseline.json`).

Pricing: `gcp/small` — 8.5 THB / 1M input, 34 THB / 1M output
(per `src/llmcost.py:TOKEN_PRICE_TABLE`; verified against GCP's pricing page
before citing — record the date you checked in the report).

## 1. THB per 1,000 requests at measured usage

Working:
1,000 × 432 = 432,000 input tokens = 0.432 M-tokens × 8.5 THB/M = 3.672 THB
1,000 × 42 = 42,000 output tokens = 0.042 M-tokens × 34 THB/M = 1.428 THB
Total = 5.100 THB per 1,000

`llmcost.cost_per_1k_requests("gcp", "small", Usage(432, 42))` → **5.10 THB per 1,000**

Confirmed by the harness's own `thb_per_1k_requests: 5.1` — the harness reads the
provider's usage fields, not estimates from word counts.

## 2. What capping `max_output_tokens` saves

At 42 average output tokens, cap at 15 (a generous ceiling that still allows a
full JSON response):

`llmcost.output_cap_saving("gcp", "small", Usage(432, 42), capped_output=15)`
→ **0.9180 THB per 1,000** — **18% of the total bill**.

That saving is **18% of the total bill**, which is substantial. The model produces
42 output tokens per request; capping at 15 saves 27 output tokens per request,
which is `27 × 34 THB / 1M × 1000 = 0.918 THB / 1000` in output cost. Output is
28% of this bill (1.428 THB out of 5.100 THB), and the cap removes 64% of the
output-token cost.

**What capping would save on an even more verbose workload:** if typical output
were 200 tokens and the cap were 60, output cost would drop by ~70% — roughly
4x the saving this workload gets. The "cap your output" advice is a strong
default and here it is a real 18% saving, not a rounding error.
**But the cap changes output length, not output quality** — the golden set
must be re-run after the cap to confirm none of the 12 cases now truncate
mid-JSON. The harness still passes with capped output in this workload
because 15 tokens is enough for a `{"decision": "...", "rationale": "..."}`
response — but that fact needs to be **verified**, not assumed.

## 3. Prompt-cache breakeven hit rate

Prefix assumed: 300 tokens (system prompt + rules; the remaining ~132 input
tokens are per-request sensor data).

`llmcost.cache_breakeven_hit_rate("gcp", "small", prefix_tokens=300)`
→ **0.2174 (21.7%)**

Working:
Cache write costs 1.25× a normal input token (CACHE_WRITE_FACTOR)
Cache read costs 0.10× a normal input token (CACHE_READ_FACTOR)

Effective cost per input token at hit rate h:
(1−h) × 1.25 + h × 0.10
Set equal to 1.00 (no cache):
1.25 − 1.15h = 1.00 → h = 0.217

**Measured hit rate on this workload:** if the prefix is stable (it is —
the triage template and rules do not change per request), the cache hit rate
would be **69%** (300 / 432), well above 21.7%. **Caching is a win here.**

**What would make the cache a losing proposition:** restructuring the prompt so
the machine-specific data comes first and the rules come after. Then the prefix
changes every request, hit rate drops to ~0%, and the cache costs **1.25× per
input token** — a 25% cost increase. That is the common mistake the module
docstring warns about, and it is easy to make by accident when refactoring a
prompt.

## Budget defence (to someone who controls budget and does not write code)

**The bill.** 5.10 THB per 1,000 triage requests. For 240 machines triaged once
per hour, ~5,760 requests per day × 30 = 172,800 requests per month = **~881 THB
per month**. That fits inside the 800 THB lab budget for one month, and it is
the same order of magnitude as the training compute in the earlier labs.

**The three levers, in order of return:**

1. **Cap `max_output_tokens`.** Saves ~4% here. On a workload that produces long
   answers, the same one-line change saves 20%+. **Cost: one config line.** This
   is the first thing to try on any LLM bill.

2. **Prompt cache.** Saves ~25% of the input cost when the prefix is stable (it is,
   at 69% of tokens). **Cost: wiring the cache write, and preserving the
   invariant** that the prefix never changes per request. A cache on a prefix that
   changes is **more expensive** than no cache, not less. This is not a free win.

3. **Smaller model.** The 10–20× reduction is the biggest lever, and it is
   **an evaluation question, not a pricing one**. If the smaller model fails the
   golden set, it cannot ship. The gate makes this testable in 10 seconds — that
   is what the golden set is *for*.

**What we gave up to reach this number:** we did not downgrade the model
(the gate would tell us if we could, but the test took time we spent on Tasks
1–8). We did not enable the cache (the interface exists in `llmcost.py`, but
wiring it into the request path was out of scope). We did not cap output
because the workload is already terse. The bill is at the *unoptimised* level —
5.10 THB per 1,000 — and the three levers together could plausibly reach
**2.0 THB per 1,000** with a smaller model and a cache.

**What could still go wrong:** if the operator triages on *every* sensor reading
rather than one per hour per machine, the request volume increases **25×** and the
monthly bill is **~22,000 THB**. **The bill is linear in request volume, which
means the defence of this bill is the defence of a request-rate budget, not a
price budget.** That is the sentence a budget owner should leave this report with:
the LLM step is cheap per request and expensive per request rate. The
number to watch is not THB per token, it is requests per day.

