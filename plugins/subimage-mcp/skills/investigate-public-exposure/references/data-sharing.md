# Public data-sharing Cypher templates

Use for targeted public snapshot or EC2 image lookups. These are public sharing paths, not network reachability paths.

## Public snapshot

```cypher
MATCH (snapshot:Snapshot)
WHERE snapshot.id = $value
   OR snapshot.name = $value
RETURN labels(snapshot) AS snapshot_labels,
       snapshot.id AS snapshot_id,
       snapshot.name AS snapshot_name,
       snapshot._ont_public AS ont_public,
       snapshot.ispublic AS is_public,
       snapshot.visibility AS visibility,
       snapshot.region AS region,
       snapshot.accountid AS account_id,
       snapshot.project_id AS project_id,
       snapshot.subscription_id AS subscription_id
LIMIT 100
```

## Public EC2 image

```cypher
MATCH (image:AWSEC2Image)
WHERE image.id = $value OR image.name = $value
RETURN labels(image) AS image_labels,
       image.id AS image_id,
       image.name AS image_name,
       image.ispublic AS is_public,
       image.owner AS owner_id,
       image.region AS region
LIMIT 100
```
