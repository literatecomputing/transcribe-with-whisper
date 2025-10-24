# GitHub Workflows Audit

Date: 2025-10-24

This document records the current triggers and artifact/upload behavior for the repository's GitHub Actions workflows and gives concrete recommendations to ensure:

- Artifact-producing workflows (docker images, Windows bundle, PyPI publish) only upload/publish artifacts for releases (tag push `v*` or `release.published`).
- Pull requests still run validation builds/tests but must not publish/upload artifacts.

---

## Summary (per-workflow)

### `ci.yml`

- Current `on:`:
  - `push` branches: `main`, `mercuryScribe0.1`
  - `pull_request` branches: `main`, `mercuryScribe0.1`
- Jobs:
  - `unit-tests`: installs deps and runs pytest (non-integration tests)
- Notes / Recommendation:
  - This is primarily a test workflow and is correctly triggered for PRs and pushes to `main`.
  - Consider extending to run lint, and a lightweight packaging smoke check on PRs.

### `docker-multiarch.yml`

- Current `on:`:
  - `workflow_dispatch` (manual)
  - `push` tags: `v*`
  - `push` branches: `main`, `fix-*`, `feature-*`
- Jobs that publish:
  - `build-and-push` uses `docker/build-push-action@v6` with `push: true` — images are pushed to GHCR on every matching push and also when manually dispatched.
  - `create-manifest` creates and pushes multi-arch manifests.
- Problem:
  - The workflow will push images when branches (e.g. `main`) are pushed. We want pushes to `main` to be validated on PRs, but only publish images on release tag pushes or release events.
- Recommendations:
  1. Add a `pull_request:` trigger to enable PR validation.
  2. Change the build step to only push images when not a pull_request. Example change for the `build-and-push` step's `uses` inputs:

```yaml
        with:
          ...
          push: ${{ github.event_name != 'pull_request' }}
```

  3. Guard `create-manifest` with an overall job condition: `if: github.event_name != 'pull_request'` (or use the tag/release test shown below).

  4. (Optional) Prefer publishing only on tag pushes or release published events. Use the expression below in upload/push conditions:

```yaml
if: (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || (github.event_name == 'release' && github.event.action == 'published')
```

### `build-windows.yml`

- Current `on:`:
  - `push` tags: `v*`
  - `pull_request` types: `[opened, synchronize, reopened]`
  - `workflow_dispatch` with `skip_smoke` input
- Jobs / artifact uploads:
  - `build-windows` job runs build script.
  - `Upload dist for manual download (even on failure)` — uses `actions/upload-artifact@v4` with `if: always()` (this will run on PRs as well).
  - `Upload built artifact` — unconditional upload step.
- Problems:
  - Both upload steps will run for PRs (first explicitly via `if: always()`) and will attach artifacts to PR runs. We want uploads only for release/tag (or manual dispatch) runs.
- Recommendations:
  - Restrict the upload steps using a release/tag check. Replace `if: always()` and the unconditional upload with the tag/release expression below so uploads only happen for tag pushes or release publishes (or optionally manual dispatch):

```yaml
if: (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || (github.event_name == 'release' && github.event.action == 'published') || github.event_name == 'workflow_dispatch'
```

  - If you want to avoid uploads for manual dispatches by default, omit `workflow_dispatch` from that expression.

Example patch for the first upload step:

```diff
-      - name: Upload dist for manual download (even on failure)
-        if: always()
-        uses: actions/upload-artifact@v4
-        with:
-          name: MercuryScribe-dist
-          path: dist/MercuryScribe
-
-      - name: Upload built artifact
-        uses: actions/upload-artifact@v4
-        with:
-          name: MercuryScribe-windows-x86_64
-          path: MercuryScribe-windows-x86_64.zip
-
+      - name: Upload dist for release/tag
+        if: (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || (github.event_name == 'release' && github.event.action == 'published')
+        uses: actions/upload-artifact@v4
+        with:
+          name: MercuryScribe-dist
+          path: dist/MercuryScribe
+
+      - name: Upload built artifact
+        if: (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || (github.event_name == 'release' && github.event.action == 'published')
+        uses: actions/upload-artifact@v4
+        with:
+          name: MercuryScribe-windows-x86_64
+          path: MercuryScribe-windows-x86_64.zip
```

### `publish-pypi.yml`

- Current `on:`:
  - `push` tags: `v*`
  - `workflow_dispatch` (manual)
- Jobs:
  - `build-and-publish` builds sdist/wheel and uses `pypa/gh-action-pypi-publish`.
- Notes / Recommendation:
  - This workflow is already gated to tag pushes; that matches the desired behavior.
  - Consider adding `release` event (published) as an alternate trigger if you sometimes create GitHub Releases instead of pushing tags directly:

```yaml
on:
  push:
    tags: ['v*']
  release:
    types: [published]
  workflow_dispatch: {}
```

---

## Suggested global policy (short)

- Validation (PRs): Run CI, unit tests, lint, and lightweight packaging/build smoke tests on `pull_request` for relevant branches. Do not upload or publish artifacts for PR runs.
- Release/Publish: Publish artifacts only when a release is created or a tag matching `v*` is pushed to the default branch. Allow `workflow_dispatch` manual runs to build artifacts, but gate uploads/publishing to an explicit condition (or require a special input to opt-in).

Standard expression to gate uploads/publish steps (copy/paste):

```yaml
if: (github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')) || (github.event_name == 'release' && github.event.action == 'published')
```

Add `|| github.event_name == 'workflow_dispatch'` if you want manual runs to also upload.

---

## Next actions (implementation plan)

1. Update `build-windows.yml` to gate upload steps (high priority).
2. Update `docker-multiarch.yml` to add `pull_request` trigger and prevent pushes on PR runs (set `push: ${{ github.event_name != 'pull_request' }}`), and gate `create-manifest`.
3. Optionally add `release` trigger to `publish-pypi.yml`.
4. Add a short `trigger-policy.md` and update README/RELEASE notes.

---

If you want, I can now implement step 1 (guarding the `build-windows.yml` upload steps) as a small patch/PR so we can validate behavior in a run. Which step should I do now?
