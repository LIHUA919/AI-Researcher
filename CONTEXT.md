# Domain Context

AI-Researcher is a verification-first, experience-driven research system. It
turns independently evaluated experiment results into bounded, cited context
for later research decisions.

## Domain language

### Research Run

One invocation of a research entrypoint for a task. A Research Run may contain
multiple Experiment Attempts and ends only after its required Verification
Record has been persisted.

### Hypothesis

A falsifiable proposed change with an expected effect, target metric, and
conditions under which the effect should hold.

### Experiment Attempt

One execution of a Hypothesis under a fixed dataset, code revision, seed,
budget, environment, Evaluation Contract, and Recall Context snapshot.

### Observation

The untrusted raw result of an Experiment Attempt: metrics, artifacts, logs,
exit status, timing, and environment data.

### Evaluation Contract

The task-specific, versioned definition of required artifacts, evaluator,
metrics, baselines, repetitions, budgets, and validity rules.

### Verification Record

The immutable result of applying an Evaluation Contract to an Observation.
Only the evaluator may write verified metrics.

### Experience Record

An immutable record combining a Hypothesis, Experiment Attempt, Observation,
Verification Record, analysis, and provenance. Invalid attempts remain
Experience Records but cannot become Knowledge Records.

### Knowledge Record

A reusable positive or negative lesson backed by one or more verified
Experience Records and an explicit promotion policy.

### Recall Context

A bounded, cited snapshot of Knowledge Records and verified Experience Records
selected for one research decision.

### Improvement Cycle

The transition from Recall Context through Hypothesis, Experiment Attempt,
Observation, Verification Record, Experience Record, and Knowledge promotion
to the next Research Run or iteration.

### Experience Gain

The paired score difference between a closed-loop run and a memory-off run
under the same task, model, seed policy, budget, dataset, evaluator, code
revision, and cache policy. For model-backed trials, the complete first
provider request is content-addressed and the byte-identical response is reused
across modes; verified recall is introduced only in later closed-loop
iterations. The reported score is the best valid evaluator-owned primary
metric within the shared fixed budget, while the full attempt trajectory is
retained. Synthetic fixtures validate reporting infrastructure but are not
evidence of Experience Gain.
