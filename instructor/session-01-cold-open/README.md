# Session 1 cold open — reproduce a stranger's result

**Instructor material.** The notebook is handed to students in class; this file is the
answer key and is not.

> **This repository is public.** A student who goes looking can find both files. The
> exercise does not depend on surprise — they still have to actually reproduce the
> number, and they still cannot — but do not leave the link in the course channel before
> the session. Hand the notebook out through the LMS, or paste it into a fresh Colab.

## What it is

[`peer-notebook.ipynb`](peer-notebook.ipynb) — one notebook by a fictional colleague,
"P. Wattana", predicting machine failure. It claims **test ROC AUC = 0.965** and says so
three times, including in the hand-over note at the bottom.

Pairs get the notebook and one instruction: **reproduce the number.** 25 minutes, then
stop whether or not it worked.

## What will happen

Nobody reproduces it. Ten honest runs land between about **0.93 and 0.98**, scattered,
never the same twice. Some pairs will get 0.961 or 0.967 and believe they succeeded —
that is the most useful outcome in the room, because the debrief takes it away from them.

Run this before class, and again on screen during the debrief:

```bash
python instructor/session-01-cold-open/spread.py --runs 10
```

```
  run    as written   grouped split
  1           0.975           0.833
  2           0.961           0.789
  ...
  Nobody reproduced 0.965: 0/10 runs hit it exactly.
  Leakage was worth +0.196 AUC — the claim was inflated before it was unstable.
```

## The five faults, and where they land

Four map onto the four locks from the concepts slide. The fifth is the punchline.

| | Fault | Lock | Where |
|---|---|---|---|
| 1 | `np.random.default_rng()` with **no seed** — the dataset itself differs every run | **Data** | data cell |
| 2 | `!pip install` unpinned, no lock file. Stored outputs say pandas 2.1.4 / sklearn 1.3.0; a student today gets neither | **Environment** | install cell |
| 3 | `joblib.dump` to `/Users/pwattana/Projects/...`, and execution counts run 1,2,3,4,5,**9**,**11** — cells 6,7,8,10 were run and are gone, so the saved state is not a top-to-bottom run | **Code** | save cell, and the whole notebook |
| 4 | No `random_state` on `train_test_split` **or** on `RandomForestClassifier` | **Randomness** | split and model cells |
| 5 | **Row-wise split on grouped data.** The label is a property of the machine; every machine has 25 rows; readings from one machine land on both sides of the split | — | split cell |

Fault 5 is not a reproducibility fault. It is the reason the number was never real, and it
is worth **+0.20 AUC**. Hold it back until the end of the debrief.

## Running the 30 minutes

| | |
|---|---|
| 0:00 | Hand out. State the task and the rule: read anything, do not contact the author, stop at 25 minutes. |
| 0:02 | They work. **Circulate and write down which fault each pair hits first.** You need those names in a moment. Do not rescue anyone. |
| 0:25 | Stop. Collect numbers on the board — every pair writes theirs up. |
| 0:30 | Move to the debrief slide. |

If a pair finishes early, hand them a second copy and ask them to make it reproducible.
That is Lab 1, and they will have started it.

## The debrief

**First, the board.** Fifteen numbers, none identical. Ask: *"which of you reproduced it?"*
Someone with 0.964 will say they did. Ask what they would say if the ops team had held
them to 0.965.

**Then sort the failures into the four locks.** Use the pairs you noted while circulating
— it lands harder when the categories come out of the room than off the slide.

**Then run `spread.py` on screen.** Ten runs, none of them 0.965. The author could not
reproduce their own number either. They were never lying; they simply never checked.

**Then the last column.** Grouped split, ~0.76. Ask what changed. Let them find it:
the label belongs to the machine, and the same machine appears on both sides. The model
was not predicting failure, it was **recognising machines it had already seen**.

Land it here:

> The number was inflated by 0.20 before it was unstable by 0.04. And every one of you
> would have shipped it.

That is the argument for the whole course, and they just produced it themselves.

## Preparation checklist

- [ ] `python instructor/session-01-cold-open/spread.py --runs 10` runs on the room machine
- [ ] Notebook uploaded to the LMS, or a Colab link ready
- [ ] A second copy for pairs who finish early
- [ ] Board or shared doc ready to collect fifteen numbers
