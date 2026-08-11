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
| `<PACKAGE_TYPE>` | Ask only if step 1 returns the same package name under several types. |
| `<IMAGE_DIGEST>` | Ask only if multiple affected images matter and the user did not scope one. |
| `<CVE_ID>` or `<ISSUE_ID>` | Optional. Use it when the user starts from a CVE or Issue URL. |

## Prerequisites

- Authenticated SubImage MCP server with vulnerability and container image scan data.
- Local source repo access is optional, but use it when available to check manifests, lockfiles, Dockerfiles, and build scripts.
- All Cypher follows `subimage-mcp:build-cypher-query` discipline: validate labels/properties with `subimageGetNodesSchema` or `searchModelQueries` before trusting a template, then run bounded read-only queries with `subimageRunCypher`.

## Workflow

### 1. Resolve the package and affected image

Start with the highest-level tool that matches the user's input:

An Issue URL or id still resolves through `subimageGetIssue(issue_id="<ISSUE_ID>")`.
A CVE id or a package name resolves against the vulnerability graph, where a
package is a `:PackageVersion` deployed on an `:Image` that a Signal affects:

Pick the predicate that matches what the user gave you. Do not `OR` the two
together: an empty `<PACKAGE_NAME>` makes `CONTAINS ''` true for every row and
the query returns 100 unrelated signals instead of the CVE's packages.

From a package name:

```cypher
MATCH (p:PackageVersion)-[:DEPLOYED]->(i:Image)
      <-[:AFFECTS]-(v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
WHERE v.status = 'active' AND toLower(p.name) CONTAINS toLower('<PACKAGE_NAME>')
RETURN DISTINCT p.name AS package, p.version AS installed,
       p.fixed_version AS fixed_in, m.id AS cve,
       v.service_image AS service_image, i.id AS image_digest
ORDER BY package, cve
LIMIT 100
```

From a CVE id, swap the predicate for `v.cve_id = toUpper('<CVE_ID>')` and keep
the rest identical.

`subimageRunCypher` takes no query parameters, so both values are inlined as
literals: escape backslashes and single quotes first (`O'Brien` becomes
`'O\'Brien'`), or the statement breaks on the apostrophe.

Use the result to pin `<PACKAGE_NAME>`, `<PACKAGE_VERSION>`, `<PACKAGE_TYPE>`, affected `service_image`, and one or more image digests. If that is already enough evidence and the user did not ask for origin, stop there. This skill exists for the origin and reachability question.

`fixed_in` is the remediation version; take it from this result rather than rederiving it later.

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

Use the layer relationship pattern returned by `subimageGetNodesSchema`; use `(:Image)-[:HAS_LAYER]->(:ImageLayer)` only when the schema confirms that direction. Keep `Image.layer_diff_ids` for ordinal position and as a fallback for providers or older tenants that have layer arrays without `HAS_LAYER`. If direction remains uncertain, run the reference's typed probe anchored to one image digest, then use the observed direction in the final query. Do not run broad unlabeled scans.

### 4. Classify origin

Use this order:

- **Application dependency**: package appears in app manifest/lockfile or in an app `pnpm install`, `npm install`, `pip install`, `go build`, or similar layer.
- **Base or parent image**: vulnerable package is on an early layer, layer history is a parent image/runtime install step, and the same layer is shared across many images.
- **Build tooling copied into runtime**: package comes from npm/pnpm/toolchain dependencies, but the runtime image copies those directories or binaries forward.
- **Scanner-only ambiguity**: graph has the package/finding but no usable layer history or manifest evidence. Say unresolved.

Only use layer evidence when a CVE/Issue finding or another source ties the package to a layer and that layer is verified as a member of the selected image. `TrivyImageFinding` is shared by vulnerability id, so a `layer_diff_id` that is not present in the selected image is not attribution for that image.

Treat `ImageLayer.history` as supporting evidence, not a classifier:

- A manifest or lockfile hit establishes application ownership even when layer history is unavailable.
- A verified early, widely shared layer with base-filesystem or runtime-install history supports base/parent origin.
- A verified app install layer plus matching manifest evidence supports application-dependency origin.
- A `COPY` layer supports copied build tooling only when the Dockerfile or repository shows the relevant files crossing stages.
- Metadata-only history (`is_empty`, `WORKDIR`, `ENV`, `USER`, `CMD`, `ENTRYPOINT`, `EXPOSE`, `HEALTHCHECK`) does not introduce filesystem packages.

For a package-only request without manifest evidence or package-to-layer attribution, report origin as unresolved; do not classify an arbitrary image layer.

Use the scanner-representations query only to confirm package presence on the selected image. Report Trivy/Syft disagreement, missing `HAS_LAYER`, or invalid finding-layer membership explicitly; scanner agreement does not by itself establish origin.

### 5. Assess reachability

Do not equate installed with exploitable. Say:

- "Installed" means the package exists in the scanned filesystem.
- "Reachable" means a running process loads the vulnerable code path with attacker-controlled input.

Check runtime code for imports, subprocess calls, archive/XML/parsing paths, exposed upload endpoints, CLI execution, and whether the affected files are copied into the runner stage. For DoS CVEs, identify what attacker-controlled input must reach the vulnerable function. If the package is base-image tooling and no runtime path uses it, classify as real package debt with weak reachability.

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
- Reformatting raw Cypher output as a table. Summarize the evidence.

## References

- Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md).
- CVE scope: `subimage-mcp:investigate-cve`.
- Image runtime/workload scope: `subimage-mcp:investigate-container`.
- Query discipline: `subimage-mcp:build-cypher-query`.
