# In-class drills

**This file documents how the drills are designed. The papers themselves are not here.**

This repository is public. Drill questions and answers live in the private instructor
repository (`../../../itcs355-instructor-private/drills/`), which has no git remote. Section A
is concept questions, and a student who reads them beforehand is sitting a different exam.

> **Exposure on record.** `drill-05.md` was committed here on 6 September 2026 with its model
> answers and was publicly readable until removed. Removal does not undo publication. Treat
> Drill 5's Section A as burned and rewrite those three questions before the final week.

Five drills, 3 marks each, 15 marks total. One at the start of each session, **two questions,
10 minutes**, closed-book except for the student's own repository.

## The shape, and why

Two questions, weighted 2 and 1.

| | Marks | Drawn from | Purpose | Marking cost |
|---|---|---|---|---|
| **Q1 — concepts** | 2 | the previous session | did they understand it | fast: one model answer, applied to every script |
| **Q2 — evidence** | 1 | **their own lab submission** | did they do it themselves | slow: their repository has to be open |

Q2 is the anti-copying mechanism and the reason the drills exist at all. It cannot be answered
from a borrowed repository, because it asks for a number or a decision specific to the student's
own submission: the parameter they varied, the permission they removed, the case in their golden
set that failed. A student who cloned a friend's lab can answer Q1 and cannot answer Q2.

**Why two questions and not six.** A cohort of 40 makes six questions 240 answers a week, and the
grading does not fit in the week. Two makes 80, and only one of the two needs a repository open.
The mechanism survives at a sixth of the cost, because one uncopyable question is as uncopyable
as three.

## Marking

Q1 carries partial credit — it asks for two things, and one of them is often right on its own.
Q2 does not: the answer is a specific value from their own work, so it matches their repository
or it does not.

Mark during the debrief slot that follows. Q1 goes quickly against the model answer; Q2 is the
one to prepare for, and most of it can be checked from their repository in advance.

## Status

All five papers are written and live in the private instructor repository, alongside
student-facing question papers for LMS upload.

| Drill | Held at start of | Covers |
|---|---|---|
| 1 | Session 2 | Session 1 + Lab 1 — reproducibility, containers, data versioning |
| 2 | Session 3 | Session 2 + Lab 2 — tracking, registries, lineage |
| 3 | Session 4 | Session 3 + Lab 3 — serving, latency, release safety |
| 4 | Session 5 | Session 4 + Lab 4 — testing, drift, incident response |
| 5 | Final week | Session 5 + Lab 5 — LLM operations, IAM, cost |
