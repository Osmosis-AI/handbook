# Osmosis managed Harbor integration

This fork preserves Surge AI's 65 tasks, prompts, MCP tools, scoring, OpenHands SDK 1.28.1, condenser and 200-call configuration. Upstream is `surge-ai/handbook@9ab14d039f2475b158634d37ef91c3d8378a13ca`. There is one official OpenHands harness.

## Ownership and patch boundary

- The official host wrapper, `agent_harness/openhands_agent.py`, is unchanged. The only runner patch keeps an SDK `ERROR` classified as a failed trial even after partial output; it does not alter successful runs. Both upstream runner copies receive the same patch and a focused regression test.
- The Osmosis Harbor repository owns `adapters/handbook`: shared-image seed uploads and SDK-native-event conversion to ATIF. The adapter calls the official wrapper; it does not reimplement the agent loop, callback persistence, prompts or tool behavior.
- This fork owns reproducible runtime packaging and the dataset release helper. Verifier dependencies are installed once with hashes. The release overlay modifies only `task.toml`, `environment/Dockerfile` and `tests/test.sh`; source tasks, rubric code and scoring remain intact.
- Do not add managed endpoint routing or frontend behavior to this fork. Those belong to the Osmosis runner/platform.

## Runtime contract

One `linux/amd64` image serves all 65 tasks. The generated task configs must reference an immutable image digest. The Harbor adapter uploads seed state to `/data` and `/initial_data`, workspace files to `/workdir`, and pristine verifier fixtures to `/environment/initial_workspace` and `/environment/initial_external_services` before official setup starts the MCP proxy. Generated Dockerfiles contain equivalent copies for force-build mode.

Generated verifier wrappers perform no package installation at runtime. They preserve upstream verifier and regression commands, fail on shell errors, and export detailed feedback to `/logs/verifier/results.json`. Rubric exception/scoring semantics remain upstream-owned.

The adapter renames the official summary to `openhands-summary.json`, retains SDK event files under `openhands-events/`, and writes ATIF as `trajectory.json` on both host and sandbox. It reads existing SDK persistence instead of changing the runner's callbacks; it never copies SDK credential state. Failure and cancellation paths attempt artifact collection without masking the original failure. These are evaluation artifacts, not a training-data contract.

Credentials still use the official process-environment allowlist. Arbitrary Harbor `--ae` overrides are not newly supported by this fork. The managed runner must supply the selected credentials in each agent process.

## Checks

```bash
uv run --directory agent_harness --locked --python 3.13 --with pytest --with openhands-sdk==1.28.1 python -m pytest tests -q
cmp agent_harness/src/agent_harness/openhands_runner.py docker/openhands-runner/openhands_runner.py
git diff --exit-code 9ab14d039f2475b158634d37ef91c3d8378a13ca -- tasks agent_harness/src/agent_harness/openhands_agent.py
```

The managed-runtime workflow builds a native amd64 image, exercises real MCP discovery/execution with scripted model responses in five network-disabled containers, then runs all 65 verifier wrappers in fresh network-disabled containers. Harbor adapter tests live with the adapter. Neither test suite substitutes for a real-model managed-platform trial.

## Release sequence

1. Review and commit both repositories, then set the workflow's `HARBOR_COMMIT` to the immutable adapter commit. After publication is authorized, run the managed-runtime workflow with `publish=true` to push the tested runtime and prepare a release-overlay artifact. Before the workflow exists on the default branch, run the same build, smoke, push and generation commands on a clean native amd64 checkout; opening a PR does not authorize merging it.
2. Review the overlay manifest: immutable source and Harbor adapter commits, runtime digest, 65 tasks and per-file hashes. Commit/tag the overlay on a dedicated dataset release branch; do not merge generated task configs back into the source branch. The workflow does not publish the dataset automatically.
3. Install the official host package from the immutable fork release in the Osmosis benchmark-runner image, together with the matching Harbor adapter. Register `handbook@<version>`, import path `adapters.handbook.agent:HandbookAgent`, and result prefix `sop-tasks/`. Verify identity against actual Harbor results.
4. Complete managed endpoint routing before activation: exact endpoint model IDs, selectable API format and custom headers are not yet integrated. Upstream OpenRouter IDs have proxy-specific semantics; do not assume generic OpenRouter routing works.
5. Run one authorized real-model trial and inspect trajectory, detailed rubric feedback and reward. Then activate the frontend catalog with the official OpenHands harness label. No runnable platform entry or source pin is enabled by this local change.

Local overlay preparation: `python3 scripts/prepare_release.py --image <repository>@sha256:<digest> --version 1.0.0 --harbor-commit <40-character-sha> --output-dir <new-directory>`. The manifest pins both host-package source and Harbor adapter code for benchmark-runner installation. `--allow-dirty` is for local validation only and records that fact in the manifest; never use it for a published dataset.

The official leaderboard uses four attempts per task. A one-attempt smoke is not leaderboard parity.

## Local validation, 2026-09-16

- 60 fork tests and 22 Harbor adapter tests passed, including pinned SDK 1.28.1 tests without skips. Ruff, scoped Harbor type checks, workflow YAML parsing, runner-copy equality and source-task/host-wrapper equality checks passed.
- The reduced native amd64 runtime (`sha256:a182238ecee9f058cd1a0147acb43ed7ef1dca0dcebea73fd761a9157c0c3f91`) passed all 65 verifier wrappers, five domain MCP smoke runs without external networking, and native-event export in a fresh SDK process. This is an unpublished local image from uncommitted source, not a release pin.
- A real `glm-5.3-flash` Docker trial on `finance_meridian_partners_158b9045` completed with no exceptions and reward `0.9108` in 4m 27s, using the official 200-call budget and supported LLM kwargs `force_string_serializer=true`, `max_tokens=16384`. An earlier attempt exposed a mounted-log copy permission error in the Harbor adapter; the fix uses Harbor's mounted-log permission normalization and has regression coverage. The fork needed no additional harness patch.
- Successful trial artifacts are on devmachine at `/tmp/handbook-live-glm53-20260916-v2/jobs/official-openhands/finance_meridian_partners_158b90__2aRAp3c/`. This verifies local Docker integration, not hosted CI, a cloud sandbox, managed endpoint routing or frontend activation. These checks preceded source commits and publication; release artifacts must be rebuilt from clean committed source.
