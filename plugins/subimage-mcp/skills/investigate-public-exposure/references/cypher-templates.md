# Cypher templates: public exposure investigation

Starting-point queries for `investigate-public-exposure`. Schema-validate first with `subimageGetNodesSchema` and `searchModelQueries`, then adjust to the live schema. Always pass the target as `$value`; never interpolate it. Each query is `LIMIT`-bounded.

## CloudFront/S3 public exposure cause

Use when the user asks whether a domain or bucket is public because of CloudFront, direct S3 bucket policy, or both. Validate the directed `(:S3Bucket)-[:POLICY_STATEMENT]->(:S3PolicyStatement)` relationship before running.

```cypher
MATCH (b:S3Bucket)
WHERE b.name = $value OR b.id = $value
OPTIONAL MATCH (cf:CloudFrontDistribution)-[r_serves:SERVES_FROM]->(b)
OPTIONAL MATCH (b)-[r_stmt:POLICY_STATEMENT]->(stmt:S3PolicyStatement)
RETURN 'bucket_name_or_id' AS match_path,
       b.id AS bucket_id, b.name AS bucket_name,
       b.anonymous_access AS bucket_anonymous_access,
       b.anonymous_actions AS bucket_anonymous_actions,
       b.block_public_policy AS bucket_block_public_policy,
       b.restrict_public_buckets AS bucket_restrict_public_buckets,
       cf.id AS cloudfront_id, cf.distribution_id AS distribution_id,
       cf.domain_name AS cloudfront_domain, cf.aliases AS cloudfront_aliases,
       cf.enabled AS cloudfront_enabled, cf.status AS cloudfront_status,
       stmt.id AS statement_id, stmt.sid AS statement_sid,
       stmt.effect AS statement_effect, stmt.principal AS statement_principal,
       stmt.action AS statement_action,
       stmt.resource AS statement_resource,
       stmt.condition AS statement_condition
UNION
MATCH (cf:CloudFrontDistribution)-[r_serves:SERVES_FROM]->(b:S3Bucket)
WHERE cf.domain_name = $value OR ANY(alias IN coalesce(cf.aliases, []) WHERE alias = $value)
OPTIONAL MATCH (b)-[r_stmt:POLICY_STATEMENT]->(stmt:S3PolicyStatement)
RETURN 'cloudfront_domain_or_alias' AS match_path,
       b.id AS bucket_id, b.name AS bucket_name,
       b.anonymous_access AS bucket_anonymous_access,
       b.anonymous_actions AS bucket_anonymous_actions,
       b.block_public_policy AS bucket_block_public_policy,
       b.restrict_public_buckets AS bucket_restrict_public_buckets,
       cf.id AS cloudfront_id, cf.distribution_id AS distribution_id,
       cf.domain_name AS cloudfront_domain, cf.aliases AS cloudfront_aliases,
       cf.enabled AS cloudfront_enabled, cf.status AS cloudfront_status,
       stmt.id AS statement_id, stmt.sid AS statement_sid,
       stmt.effect AS statement_effect, stmt.principal AS statement_principal,
       stmt.action AS statement_action,
       stmt.resource AS statement_resource,
       stmt.condition AS statement_condition
LIMIT 100
```

## Direct S3 bucket policy statements

Use when the target bucket is already known and the answer requires policy-statement details.

```cypher
MATCH (b:S3Bucket)-[:POLICY_STATEMENT]->(stmt:S3PolicyStatement)
WHERE b.name = $value OR b.id = $value
RETURN b.id AS bucket_id,
       b.name AS bucket_name,
       b.anonymous_access AS bucket_anonymous_access,
       b.anonymous_actions AS bucket_anonymous_actions,
       stmt.id AS statement_id,
       stmt.sid AS statement_sid,
       stmt.effect AS statement_effect,
       stmt.principal AS statement_principal,
       stmt.action AS statement_action,
       stmt.resource AS statement_resource,
       stmt.condition AS statement_condition
LIMIT 100
```
