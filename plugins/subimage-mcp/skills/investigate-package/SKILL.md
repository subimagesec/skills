---
name: investigate-package
description: Trace a package or dependency in SubImage from CVE or issue to package node, image, layer history, base-image versus application origin, and practical reachability. Use when the user asks "where does this package come from", "is this from the base image", "is this installed package exploitable", "trace package origin", or "why is package X on this image".
---

# Investigate package origin

## What this does

Answers why a package exists on an image and whether "installed" means "reachable." The workflow ties SubImage's vulnerability/package tools to graph evidence: package node, affected image, exact image layer, layer history, and source repo or lockfile clues.

## When to use

✅ User asks where a package came from after a CVE or Issue triage.
✅ User asks whether a vulnerable package is from the base image, parent image, runtime tooling, or app dependencies.
✅ User asks whether software being present on an image makes it exploitable.
✅ User gives a package name/version, image digest/tag, CVE id, or SubImage Issue URL and wants to identify where the package came from.

❌ User only wants a CVE impact summary: use `subimage-mcp:investigate-cve`.
❌ User only wants where an image runs: use `subimage-mcp:investigate-container`.
❌ User wants a free-form graph query unrelated to packages or layers: use `subimage-mcp:build-cypher-query`.

## Required inputs

| Value | If missing, ask |
|---|---|
| `<PACKAGE_NAME>` | "Which package should I trace?" |
| `<PACKAGE_VERSION>` | Ask only if multiple versions appear. |
| `<PACKAGE_TYPE>` | Ask only if `subimageGetPackageDetails` reports ambiguous types. |
| `<IMAGE_DIGEST>` | Ask only if multiple affected images matter and the user did not scope one. |
| `<CVE_ID>` or `<ISSUE_ID>` | Optional. Use it when the user starts from a CVE or Issue URL. |

## Prerequisites

- Authenticated SubImage MCP server with vulnerability and container image scan data.
- Local source repo access is optional, but use it when available to check manifests, lockfiles, Dockerfiles, and build scripts.
- All Cypher follows `subimage-mcp:build-cypher-query` discipline: validate labels/properties with `subimageGetNodesSchema` or `searchModelQueries` before trusting a template, then run bounded read-only queries with `subimageRunCypher`.

## Workflow

### 1. Resolve the package and affected image

Start with the highest-level tool that matches the user's input:

- Issue URL or id: `subimageGetIssue(issue_id="<ISSUE_ID>")`.
- CVE id: `subimageGetVulnerabilityDetails(cve_id="<CVE_ID>")`.
- Package name: `subimageListPackages(package_name="<PACKAGE_NAME>")`, then `subimageGetPackageDetails(package_name="<PACKAGE_NAME>", package_type="<PACKAGE_TYPE>")`.

Use those results to pin `<PACKAGE_NAME>`, `<PACKAGE_VERSION>`, `<PACKAGE_TYPE>`, affected `service_image`, and one or more image digests. If the structured tool already has enough evidence and the user did not ask for origin, stop there. This skill exists for the origin and reachability question.

### 2. Check application ownership before graph archaeology

If a local repo is available, search the relevant manifest and lockfiles:

```bash
rg -n '"<PACKAGE_NAME>"|<PACKAGE_NAME>@|<PACKAGE_VERSION>' package.json pnpm-lock.yaml yarn.lock package-lock.json
```

For non-JavaScript packages, use the closest manifest (`requirements*.txt`, `pyproject.toml`, `go.mod`, `Cargo.lock`, `Gemfile.lock`, OS package install lines, Dockerfile package manager commands). A hit in an app manifest is app-owned evidence. No hit is not proof of base image origin; continue to graph.

### 3. Trace package to image and layer

Load [`references/cypher-templates.md`](references/cypher-templates.md), validate the labels/properties you will use, and run the smallest query set needed:

1. Package nodes.
2. Package on image.
3. CVE finding layer and image layer membership, when a CVE is in scope.
4. Layer position and history.
5. Shared-layer count, when deciding base image versus app layer.
6. Fix versions, when the user needs the remediation target (§ Fix versions).
7. Severity landscape, when the image's overall or per-layer finding load gives useful context (§ Severity landscape).

Use the layer relationship pattern returned by `subimageGetNodesSchema`; use `(:Image)-[:HAS_LAYER]->(:ImageLayer)` only when the schema confirms that direction. Keep `Image.layer_diff_ids` for ordinal position and as a fallback for providers or older tenants that have layer arrays without `HAS_LAYER`. If direction remains uncertain, run the reference's typed probe anchored to one image digest, then use the observed direction in the final query. Do not run broad unlabeled scans.

### 4. Classify origin

Use this order:

- **Application dependency**: package appears in app manifest/lockfile or in an app `pnpm install`, `npm install`, `pip install`, `go build`, or similar layer.
- **Base or parent image**: vulnerable package is on an early layer, layer history is a parent image/runtime install step, and the same layer is shared across many images.
- **Build tooling copied into runtime**: package comes from npm/pnpm/toolchain dependencies, but the runtime image copies those directories or binaries forward.
- **Scanner-only ambiguity**: graph has the package/finding but no usable layer history or manifest evidence. Say unresolved.

To place a layer in one of those categories, read the `ImageLayer.history` (and `is_empty`) for the layer that carries the finding and match the strongest signal below. Signals are heuristics on Docker history text, not guarantees; when a layer matches more than one, prefer the most specific.

| Layer signal in `history` (or `is_empty`) | Layer class | Origin reading |
|---|---|---|
| `debian`, `ubuntu`, `alpine`, `bookworm`, base filesystem create | base OS | inherited from the base/parent OS layer |
| `apt-get update/upgrade/install`, `apk add`, `yum install`, `dnf install` | base-image OS packages | OS packages installed in the base/parent image |
| `python.tar.xz`, `make install`, `lib*-dev` (e.g. `libssl-dev`, `zlib1g-dev`), `node`, `go build` | runtime build | runtime or runtime build dependency |
| `pip install`, `uv sync`, `poetry install`, `npm install`/`npm ci`, `yarn install`, `pnpm install`, `bundle install`, `go mod download` | application dependency | application dependency install |
| `COPY . .`, `COPY src`, `COPY app`, `ADD .` | application code | application code; not a package unless a finding links here |
| `is_empty = true`, `WORKDIR`, `ENV`, `USER`, `CMD`, `ENTRYPOINT`, `EXPOSE`, `HEALTHCHECK` | metadata | should not introduce package debt |

A finding on a base-OS or base-image-OS-packages layer points at base-image remediation; one on an application-dependency layer points at a manifest/lockfile bump. See the § Layer history template for the query that returns `history`.

### 5. Assess reachability

Do not equate installed with exploitable. Say:

- "Installed" means the package exists in the scanned filesystem.
- "Reachable" means a running process loads the vulnerable code path with attacker-controlled input.

Check runtime code for imports, subprocess calls, archive/XML/parsing paths, exposed upload endpoints, CLI execution, and whether the affected files are copied into the runner stage. For DoS CVEs, identify what attacker-controlled input must reach the vulnerable function. If the package is base-image tooling and no runtime path uses it, classify as real package debt with weak reachability.

### 6. Grade the evidence

Two scanners feed the graph: Trivy (`TrivyPackage`, `TrivyImageFinding`) and Syft (`SyftPackage`). Cross-check them against the canonical `Package` and the layer attribution, and state a confidence grade so the reader knows how much to trust the origin call:

- **Strong**: canonical `Package` on the image, confirmed by both `TrivyPackage` and `SyftPackage` **for that same image**, with the finding tied to a concrete `ImageLayer` that has history. Get the two scanner confirmations from the § Scanner representations query anchored to `<IMAGE_DIGEST>` via `DEPLOYED`; a scanner detection on some other image does not qualify.
- **Medium**: Trivy reports the package/finding and layer attribution exists, but Syft confirmation is missing.
- **Weak**: finding is on the image, but the canonical `Package`, the Syft package, or the layer attribution is missing. Origin is inferred, not proven.

Flag these mismatches explicitly rather than smoothing them over, and name the fallback you used:

- Trivy reports a vulnerable package but Syft detects no matching package: possible false positive or scanner gap, hold at medium and say so.
- Syft detects the package but no canonical `Package` link exists: report from the Syft node and note the missing normalization.
- `Image.layer_diff_ids` is populated but `HAS_LAYER` returns nothing: use the array form (see the templates' fallback queries) and say the relationship is absent for this tenant.
- A finding carries `layer_diff_id` but no `ImageLayer` matches it: layer history is unavailable, so origin stays unresolved.
- A fix exists on `TrivyPackage`/finding but not on the canonical `Package` (or vice versa): report the fix version you found and which node carried it.

## Output

```markdown
# Package origin: <PACKAGE_NAME>@<PACKAGE_VERSION>

## Finding
- source input: <issue/CVE/package>
- package: <name>@<version> (<type>)
- image: <service_image> <digest>
- fix: <fix version or none>

## Origin
- classification: <application dependency | base image | build tooling copied into runtime | unresolved>
- evidence: <manifest hit, layer index, layer history summary, shared-layer count>

## Reachability
- installed: yes/no
- reachable from normal runtime: likely / unlikely / unknown
- reason: <one or two lines>

## Recommendation
<bump package, bump base image, rebuild image, remove copied tooling, monitor, or accept risk>
```

## Verification

- Cite the exact MCP facts used: package purl, image digest, layer diff id, and layer history summary.
- If you used repo search, cite the file hit or say no manifest hit was found.
- If graph layer history is missing, say package origin is unresolved instead of inferring parent-image origin.

## Anti-patterns

- Saying "installed means exploitable." Installed is inventory; reachability is data flow into the vulnerable code path.
- Calling a package "base image" only because the remediation plan says so. Prove it with layer history or say it is inferred from the remediation tool.
- Trusting `base_image_sources` alone. It can be empty even when layer history clearly shows parent image origin.
- Running the package neighbor query and stopping there. The layer query is what separates app-owned dependency from parent/runtime tooling.
- Grading evidence as strong when only one scanner sees the package. Flag Trivy/Syft disagreement instead of hiding it.
- Reformatting raw Cypher output as a table. Summarize the evidence.

## References

- Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md).
- CVE scope: `subimage-mcp:investigate-cve`.
- Image runtime/workload scope: `subimage-mcp:investigate-container`.
- Query discipline: `subimage-mcp:build-cypher-query`.
