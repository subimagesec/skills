---
name: investigate-package
description: Trace a package or dependency in SubImage from CVE or issue to package node, image, layer history, base-image versus application origin, and practical reachability. Use when the user asks "where does this package come from", "is this from the base image", "is this installed package exploitable", "trace package provenance", or "why is package X on this image".
---

# Investigate package provenance

## What this does

Answers why a package exists on an image and whether "installed" means "reachable." The workflow ties SubImage's vulnerability/package tools to graph evidence: package node, affected image, exact image layer, layer history, and source repo or lockfile clues.

## When to use

✅ User asks where a package came from after a CVE or Issue triage.
✅ User asks whether a vulnerable package is from the base image, parent image, runtime tooling, or app dependencies.
✅ User asks whether software being present on an image makes it exploitable.
✅ User gives a package name/version, image digest/tag, CVE id, or SubImage Issue URL and wants root-cause provenance.

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
3. CVE finding layer, when a CVE is in scope.
4. Layer history.
5. Shared-layer count, when deciding base image versus app layer.

Use bounded, read-only `subimageRunCypher` calls. If a relationship direction is uncertain, use the undirected diagnostic templates in the reference, then summarize the direction you observed. Do not run broad unlabeled scans.

### 4. Classify origin

Use this order:

- **Application dependency**: package appears in app manifest/lockfile or in an app `pnpm install`, `npm install`, `pip install`, `go build`, or similar layer.
- **Base or parent image**: vulnerable package is on an early layer, layer history is a parent image/runtime install step, and the same layer is shared across many images.
- **Build tooling copied into runtime**: package comes from npm/pnpm/toolchain dependencies, but the runtime image copies those directories or binaries forward.
- **Scanner-only ambiguity**: graph has the package/finding but no usable layer history or manifest evidence. Say unresolved.

### 5. Assess reachability

Do not equate installed with exploitable. Say:

- "Installed" means the package exists in the scanned filesystem.
- "Reachable" means a running process loads the vulnerable code path with attacker-controlled input.

Check runtime code for imports, subprocess calls, archive/XML/parsing paths, exposed upload endpoints, CLI execution, and whether the affected files are copied into the runner stage. For DoS CVEs, identify what attacker-controlled input must reach the vulnerable function. If the package is base-image tooling and no runtime path uses it, classify as real package debt with weak reachability.

## Output

```markdown
# Package provenance: <PACKAGE_NAME>@<PACKAGE_VERSION>

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
- If graph layer history is missing, say provenance is unresolved instead of inferring parent-image origin.

## Anti-patterns

- Saying "installed means exploitable." Installed is inventory; reachability is data flow into the vulnerable code path.
- Calling a package "base image" only because the remediation plan says so. Prove it with layer history or say it is inferred from the remediation tool.
- Trusting `base_image_sources` alone. It can be empty even when layer history clearly shows parent image origin.
- Running the package neighbor query and stopping there. The layer query is what separates app-owned dependency from parent/runtime tooling.
- Reformatting raw Cypher output as a table. Summarize the evidence.

## References

- Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md).
- CVE scope: `subimage-mcp:investigate-cve`.
- Image runtime/workload scope: `subimage-mcp:investigate-container`.
- Query discipline: `subimage-mcp:build-cypher-query`.
