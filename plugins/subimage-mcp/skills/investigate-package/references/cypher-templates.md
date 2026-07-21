# Package Provenance Cypher Templates

Starting-point queries for `investigate-package`. Replace `<...>` values before calling `subimageRunCypher`. Keep every query read-only and `LIMIT`-bounded. These templates intentionally use undirected relationships where the goal is diagnostic provenance; if a final answer depends on direction, report the observed `type(r)` and direction from the result.

## Package nodes

Use these to see whether the package is represented as Trivy, Syft, and ontology nodes. Run only the variants you need.

```cypher
MATCH (p:TrivyPackage)
WHERE p.name = '<PACKAGE_NAME>' AND coalesce(p.version, p.installed_version, '') = '<PACKAGE_VERSION>'
RETURN labels(p) AS labels, keys(p) AS keys, p AS node
LIMIT 20
```

```cypher
MATCH (p:SyftPackage)
WHERE p.name = '<PACKAGE_NAME>' AND coalesce(p.version, '') = '<PACKAGE_VERSION>'
RETURN labels(p) AS labels, keys(p) AS keys, p AS node
LIMIT 20
```

```cypher
MATCH (p:Package)
WHERE p.name = '<PACKAGE_NAME>' AND coalesce(p.version, '') = '<PACKAGE_VERSION>'
RETURN labels(p) AS labels, keys(p) AS keys, p AS node
LIMIT 20
```

If the version is unknown, drop the version predicates and keep the same `LIMIT`.

## Package neighbor probe

Use this to discover images, findings, fixes, and scanner aliases attached to the package.

```cypher
MATCH (p:TrivyPackage {name:'<PACKAGE_NAME>'})-[r]-(n)
WHERE coalesce(p.version, p.installed_version, '') = '<PACKAGE_VERSION>'
RETURN type(r) AS rel, labels(n) AS neighbor_labels, keys(n) AS neighbor_keys, n AS neighbor
LIMIT 50
```

## Package deployed on image

Use this when you have an affected image digest and need to prove the package is on that image.

```cypher
MATCH (i:Image)-[r]-(p:TrivyPackage {name:'<PACKAGE_NAME>'})
WHERE i.digest = '<IMAGE_DIGEST>'
  AND coalesce(p.version, p.installed_version, '') = '<PACKAGE_VERSION>'
RETURN labels(i) AS image_labels, i.digest AS image_digest, type(r) AS rel_type, p.purl AS purl
LIMIT 20
```

## CVE finding layer on image

Use this when a CVE is in scope. It ties the CVE finding and package to the exact image layer.

```cypher
MATCH (f:TrivyImageFinding {cve_id:'<CVE_ID>'})--(p:TrivyPackage {name:'<PACKAGE_NAME>'})
MATCH (i:Image)--(f)
WHERE i.digest = '<IMAGE_DIGEST>'
  AND coalesce(p.version, p.installed_version, '') = '<PACKAGE_VERSION>'
RETURN p.purl AS purl,
       f.layer_diff_id AS finding_layer_diff_id,
       f.layer_digest AS finding_layer_digest,
       i.digest AS image_digest,
       i.source_file AS source_file,
       i.source_revision AS source_revision,
       i.layer_diff_ids[0] AS layer0,
       i.layer_diff_ids[1] AS layer1,
       i.layer_diff_ids[2] AS layer2
LIMIT 20
```

## Layer index in image

Use this to prove whether the vulnerable layer is early parent-image material or later app build output.

```cypher
MATCH (i:Image {digest:'<IMAGE_DIGEST>'})
UNWIND range(0, size(i.layer_diff_ids) - 1) AS idx
WITH i, idx, i.layer_diff_ids[idx] AS layer_diff_id
WHERE layer_diff_id = '<LAYER_DIFF_ID>'
RETURN i.digest AS image_digest,
       idx AS layer_index,
       layer_diff_id AS layer_diff_id,
       i.source_file AS source_file,
       i.source_revision AS source_revision
LIMIT 10
```

## Layer history

Use this to inspect the Docker history entry for the layer. The history text usually shows whether the layer came from a parent runtime image, package-manager install, or app build command.

```cypher
MATCH (l:ECRImageLayer)
WHERE l.diff_id = '<LAYER_DIFF_ID>'
   OR l.id = '<LAYER_DIFF_ID>'
   OR l.id = '<LAYER_DIGEST>'
   OR l.digest = '<LAYER_DIGEST>'
RETURN l.diff_id AS diff_id,
       l.id AS id,
       left(l.history, 1000) AS history_prefix
LIMIT 5
```

## Shared layer count

Use this to support a base-image classification. A layer reused by many images is usually parent image/runtime tooling; a layer unique to one service is more likely app-owned.

```cypher
MATCH (i:Image)
WHERE '<LAYER_DIFF_ID>' IN coalesce(i.layer_diff_ids, [])
RETURN count(DISTINCT i) AS image_count,
       collect(DISTINCT i.source_file)[0..10] AS sample_source_files
LIMIT 1
```

## Image layer summary

Use this when no CVE finding exists but you have an image digest and need nearby layer context.

```cypher
MATCH (i:Image {digest:'<IMAGE_DIGEST>'})
RETURN i.digest AS image_digest,
       i.source_file AS source_file,
       i.source_revision AS source_revision,
       i.layer_diff_ids[0..8] AS first_layers,
       size(i.layer_diff_ids) AS layer_count
LIMIT 10
```
