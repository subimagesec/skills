# Package Origin Cypher Templates

Starting-point queries for `investigate-package`. Validate every label, property, relationship, and direction with `subimageGetNodesSchema` before use. Keep every query read-only, filtered early, and `LIMIT`-bounded.

`subimageRunCypher` does not accept separate query parameters. Before replacing a `<..._LITERAL>` placeholder, escape the external value in this order: `\` as `\\`, `'` as `\'`, carriage return as `\r`, and newline as `\n`; then surround it with single quotes. Never insert raw user input into a query.

## Package nodes

Start from the canonical package node. It preserves package-to-image traversal for Trivy-only, Syft-only, and multi-scanner packages.

```cypher
MATCH (p:Package)
WHERE p.name = <PACKAGE_NAME_LITERAL> AND p.version = <PACKAGE_VERSION_LITERAL>
RETURN p.name AS package_name,
       p.version AS package_version,
       p.type AS package_type,
       p.purl AS purl
LIMIT 20
```

If the version is unknown, drop the version predicates and keep the same `LIMIT`.

## Scanner representations

Use this only when scanner-specific evidence matters.

```cypher
MATCH (p:Package)
WHERE p.name = <PACKAGE_NAME_LITERAL> AND p.version = <PACKAGE_VERSION_LITERAL>
OPTIONAL MATCH (p)-[trivyDetected:DETECTED_AS]->(trivy:TrivyPackage)
OPTIONAL MATCH (p)-[syftDetected:DETECTED_AS]->(syft:SyftPackage)
RETURN p.purl AS canonical_purl,
       collect(DISTINCT trivy.purl)[0..10] AS trivy_purls,
       collect(DISTINCT syft.purl)[0..10] AS syft_purls
LIMIT 20
```

## Package deployed on image

Use this when you have an affected image digest and need to prove the package is on that image.

```cypher
MATCH (p:Package)-[deployed:DEPLOYED]->(i:Image)
WHERE p.name = <PACKAGE_NAME_LITERAL>
  AND p.version = <PACKAGE_VERSION_LITERAL>
  AND coalesce(i.digest, i._ont_digest) = <IMAGE_DIGEST_LITERAL>
RETURN labels(i) AS image_labels,
       coalesce(i.digest, i._ont_digest) AS image_digest,
       type(deployed) AS rel_type,
       p.purl AS purl
LIMIT 20
```

## CVE finding layer on image

Use this when a CVE is in scope. It ties the CVE finding and package to the exact image layer.

```cypher
MATCH (f:TrivyImageFinding)-[affectsPackage:AFFECTS]->(p:Package)
MATCH (f)-[affectsImage:AFFECTS]->(i:Image)
WHERE f.cve_id = <CVE_ID_LITERAL>
  AND p.name = <PACKAGE_NAME_LITERAL>
  AND p.version = <PACKAGE_VERSION_LITERAL>
  AND coalesce(i.digest, i._ont_digest) = <IMAGE_DIGEST_LITERAL>
OPTIONAL MATCH (i)-[hasLayer:HAS_LAYER]->(memberLayer:ImageLayer)
WHERE memberLayer.diff_id = f.layer_diff_id
OPTIONAL MATCH (fallbackLayer:ImageLayer {diff_id: f.layer_diff_id})
WHERE f.layer_diff_id IN coalesce(i.layer_diff_ids, [])
WITH f, p, i, coalesce(memberLayer, fallbackLayer) AS layer
RETURN p.purl AS purl,
       f.layer_diff_id AS finding_layer_diff_id,
       f.layer_digest AS finding_layer_digest,
       coalesce(i.digest, i._ont_digest) AS image_digest,
       i.source_file AS source_file,
       i.source_revision AS source_revision,
       CASE WHEN layer IS NULL THEN [] ELSE labels(layer) END AS layer_labels,
       left(coalesce(layer.history, ''), 1000) AS layer_history_prefix,
       i.layer_diff_ids[0] AS layer0,
       i.layer_diff_ids[1] AS layer1,
       i.layer_diff_ids[2] AS layer2
LIMIT 20
```

## Layer index in image

Use this to prove whether the vulnerable layer is early parent-image material or later app build output.

```cypher
MATCH (i:Image)
WHERE coalesce(i.digest, i._ont_digest) = <IMAGE_DIGEST_LITERAL>
UNWIND range(0, size(i.layer_diff_ids) - 1) AS idx
WITH i, idx, i.layer_diff_ids[idx] AS layer_diff_id
WHERE layer_diff_id = <LAYER_DIFF_ID_LITERAL>
OPTIONAL MATCH (i)-[hasLayer:HAS_LAYER]->(memberLayer:ImageLayer {diff_id: layer_diff_id})
OPTIONAL MATCH (fallbackLayer:ImageLayer {diff_id: layer_diff_id})
WITH i, idx, layer_diff_id, coalesce(memberLayer, fallbackLayer) AS layer
RETURN coalesce(i.digest, i._ont_digest) AS image_digest,
       idx AS layer_index,
       layer_diff_id AS layer_diff_id,
       CASE WHEN layer IS NULL THEN [] ELSE labels(layer) END AS layer_labels,
       left(coalesce(layer.history, ''), 1000) AS layer_history_prefix,
       i.source_file AS source_file,
       i.source_revision AS source_revision
LIMIT 10
```

## Layer history

Use this to inspect the Docker history entry for the layer. The history text usually shows whether the layer came from a parent runtime image, package-manager install, or app build command.

```cypher
MATCH (i:Image)
WHERE coalesce(i.digest, i._ont_digest) = <IMAGE_DIGEST_LITERAL>
OPTIONAL MATCH (i)-[hasLayer:HAS_LAYER]->(memberLayer:ImageLayer {diff_id: <LAYER_DIFF_ID_LITERAL>})
OPTIONAL MATCH (fallbackLayer:ImageLayer {diff_id: <LAYER_DIFF_ID_LITERAL>})
WITH i, memberLayer, fallbackLayer
WHERE memberLayer IS NOT NULL OR <LAYER_DIFF_ID_LITERAL> IN coalesce(i.layer_diff_ids, [])
WITH i, coalesce(memberLayer, fallbackLayer) AS layer
RETURN coalesce(i.digest, i._ont_digest) AS image_digest,
       CASE WHEN layer IS NULL THEN [] ELSE labels(layer) END AS layer_labels,
       layer.diff_id AS diff_id,
       layer.id AS id,
       layer.digest AS compressed_digest,
       left(coalesce(layer.history, ''), 1000) AS history_prefix
LIMIT 5
```

## Shared layer count

Use this to support a base-image classification. A layer reused by many images is usually parent image/runtime tooling; a layer unique to one service is more likely app-owned.

```cypher
MATCH (layer:ImageLayer {diff_id: <LAYER_DIFF_ID_LITERAL>})<-[hasLayer:HAS_LAYER]-(i:Image)
RETURN count(DISTINCT i) AS image_count,
       collect(DISTINCT i.source_file)[0..10] AS sample_source_files
LIMIT 1
```

If that returns zero but the image has `layer_diff_ids`, fall back to the array form for providers or older tenants without `HAS_LAYER`:

```cypher
MATCH (i:Image)
WHERE <LAYER_DIFF_ID_LITERAL> IN coalesce(i.layer_diff_ids, [])
RETURN count(DISTINCT i) AS image_count,
       collect(DISTINCT i.source_file)[0..10] AS sample_source_files
LIMIT 1
```

## Image layer summary

Use this when no CVE finding exists but you have an image digest and need nearby layer context.

```cypher
MATCH (i:Image)
WHERE coalesce(i.digest, i._ont_digest) = <IMAGE_DIGEST_LITERAL>
UNWIND range(0, size(i.layer_diff_ids) - 1) AS idx
WITH i, idx, i.layer_diff_ids[idx] AS layer_diff_id
OPTIONAL MATCH (i)-[hasLayer:HAS_LAYER]->(memberLayer:ImageLayer {diff_id: layer_diff_id})
OPTIONAL MATCH (fallbackLayer:ImageLayer {diff_id: layer_diff_id})
WITH i, idx, layer_diff_id, head(collect(coalesce(memberLayer, fallbackLayer))) AS layer
ORDER BY idx
WITH i, collect({
  layer_index: idx,
  diff_id: layer_diff_id,
  history_prefix: left(coalesce(layer.history, ''), 240)
}) AS ordered_layer_nodes
RETURN coalesce(i.digest, i._ont_digest) AS image_digest,
       i.source_file AS source_file,
       i.source_revision AS source_revision,
       i.layer_diff_ids[0..8] AS first_layers,
       size(i.layer_diff_ids) AS layer_count,
       ordered_layer_nodes[0..8] AS first_layer_nodes
LIMIT 10
```

## Layer relationship direction probe

Run this only when `subimageGetNodesSchema` lists `HAS_LAYER` but its direction is still unclear. Anchor it to one image; an unfiltered relationship probe can time out on large tenants.

```cypher
MATCH (i:Image)-[hasLayer:HAS_LAYER]-(layer:ImageLayer)
WHERE coalesce(i.digest, i._ont_digest) = <IMAGE_DIGEST_LITERAL>
RETURN labels(startNode(hasLayer)) AS start_labels,
       type(hasLayer) AS rel_type,
       labels(endNode(hasLayer)) AS end_labels,
       layer.diff_id AS layer_diff_id
LIMIT 5
```
