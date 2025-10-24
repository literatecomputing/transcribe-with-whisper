# CI Trigger Policy

Date: 2025-10-24

Purpose
-------
This file documents the repository policy for GitHub Actions triggers used by the transcribe-with-whisper project. The goal is to have clear, predictable CI behavior:

- Pull requests (PRs) run validation (tests, lint, light packaging builds) but must not publish or upload release artifacts.
- Releases (either a pushed tag like `v1.2.3` or a GitHub Release published event) cause the workflows that produce distributable artifacts to upload/publish those artifacts.
- Manual runs (`workflow_dispatch`) are available for maintainers to build artifacts on-demand; whether those manual runs publish artifacts is decided per-workflow.

Key concepts: tags vs releases
--------------------------------
- Git tag (`git tag v1.2.3`) is a git reference. A push of a tag generates a `push` event where `github.ref` will be `refs/tags/v1.2.3`.
- GitHub Release is a higher-level object in the GitHub web UI that is frequently associated with a tag. When a Release is published via the GitHub UI (or API), GitHub will send a `release` event with `action: published`.

Which to use?
- Preferred: create an annotated tag and push it (example: `git tag -a v1.2.3 -m "Release v1.2.3" && git push origin v1.2.3`). The CI listens for tag pushes and will perform the release builds.
- Alternative: create a GitHub Release in the web UI, which usually creates a tag for you. Workflows that listen for the `release.published` event will also run and can be used to publish artifacts.

General trigger recommendations
-------------------------------
- For validation on PRs use `pull_request` triggers (types: opened, synchronize, reopened). PR jobs should not publish artifacts.
- For publishing artifacts use either `push` tags (`refs/tags/v*`) or `release` published events. Optionally keep `workflow_dispatch` for manual builds.

Standard guard expression for steps that upload or publish artifacts
--------------------------------------------------------------------
Use this expression to protect any upload/publish step so it only runs for tag pushes, release publishes, or explicit manual runs:

```yaml
if: |
  (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) ||
  (github.event_name == 'release' && github.event.action == 'published') ||
  github.event_name == 'workflow_dispatch'
```

Notes on manual runs
--------------------
- If you want manual runs to _build_ but not publish artifacts, omit `workflow_dispatch` from the guard expression and instead add a required `inputs.publish` boolean to the `workflow_dispatch` so the manual runner must opt-in to publishing.

Examples
--------
- Docker build step (`docker/build-push-action`) that should only push on release/tag or manual runs:

```yaml
with:
  push: ${{ (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || github.event_name == 'workflow_dispatch' }}
```

- Upload artifact step that should only run for releases/tags/manual runs:

```yaml
- name: Upload dist
  if: |
    (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) ||
    (github.event_name == 'release' && github.event.action == 'published') ||
    github.event_name == 'workflow_dispatch'
  uses: actions/upload-artifact@v4
  with:
    name: MercuryScribe-dist
    path: dist/MercuryScribe
```

Permissions and secrets
-----------------------
- Publishing to external registries (PyPI, GHCR) requires repository secrets and appropriate `permissions` in the workflow. Ensure the publishing job sets/requests only the minimum permissions necessary.

Rollout plan for this repo
--------------------------
1. Apply guarded upload/publish expressions to all artifact-producing workflows.
2. Ensure PR builds include a lightweight packaging smoke test (no publish).
3. Document the release flow in `README.md` and add pointers to this policy.

If you want a different behavior (e.g. publishing from `main` pushes instead of tags), adjust the guard expression in this file and the workflows accordingly, but prefer tags/releases for reproducibility.
