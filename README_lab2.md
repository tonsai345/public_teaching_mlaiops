## Promotion Ownership (Task 4)

**Who should own promotion to Staging:**
The **ML engineer who trained the model** — the person who owns the training
pipeline and can trace the run. In this course, that's the student. In a real
organisation, it's the engineer on rotation for that model, not a manager and
not a platform admin. The person who produced the artefact is the person who
understands its failure modes.

**Who should own promotion to Production:**
A **second engineer, not the one who trained the model** — a reviewer on a
different team or at least a different shift. This is the four-eyes principle:
the person who is emotionally invested in the metric cannot be the person who
signs off on the risk.

**Evidence required at each gate:**

*For Staging:*
- All 8 lineage fields populated and verifiable (`git_commit` reachable, `data_version` resolvable via DVC, `image_digest` present in ACR)
- `metric_test` within the tolerance claimed in the justification
- The 200-word justification exists and names a real weakness
- `reload_check.py` passes from the registry

*For Production:*
- The Staging version has run for at least one week under real or shadow traffic
- Drift monitor shows no unexplained shift in the input distribution
- A cost estimate for the endpoint at expected traffic is attached and approved
- A rollback plan exists: the previous Production version is still registered and its image digest is still pullable
