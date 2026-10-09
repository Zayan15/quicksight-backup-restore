# Validation record

## Offline validation

Ten unit tests passed locally on October 9, 2026. They cover success, every documented terminal failure state, unknown statuses, bounded waits, throttling retries and timeouts, access errors, paginated S3 discovery, invalid configuration, invalid S3 URIs, and unique backup names. These tests exercise operation helpers with fake clocks and mock clients; they do not establish live AWS compatibility.

## Authorized sandbox procedure — not yet executed

1. Use a dedicated sandbox AWS profile, a synthetic QuickSight dashboard and dataset, and a private S3 bucket. Never use employer resources or production dashboards.
2. Grant only the QuickSight export/import/describe/list permissions and S3 list/read/write access required for those sandbox resources. Review any KMS requirements separately.
3. Record Python and dependency versions, region, resource types, and a sanitized test identifier. Keep account IDs, ARNs, bucket names, URLs, and credentials out of public records.
4. Export the synthetic dashboard. Verify a nonempty `.qs` object appears. Repeat and verify a distinct object key.
5. Confirm that restoring is disabled until the acknowledgment checkbox is selected. Import only into the isolated test environment, accounting for resource IDs that may be overwritten.
6. Inspect the restored dashboard, dataset references, visuals, permissions, and any credentials that must be configured manually. Record pass/fail with a redacted screenshot.
7. Exercise a denied-permission case and inspect the reported error. Test deadline behavior offline instead of deliberately stalling paid resources.
8. Remove only the disposable test resources you created after reviewing their names. Record cleanup completion and any remaining costs.

## Current limitations

Live AWS validation has **not** been performed. The local timeout bounds polling sleeps; SDK retries and individual network calls add latency. Download requests have connect/read timeouts, but bundles are still buffered in memory. Restoration can update existing resources. Imported connections and datasets may need environment-specific configuration. No recovery guarantee or production readiness claim is made.
