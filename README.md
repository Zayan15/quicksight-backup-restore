# QuickSight Backup & Restore

## Overview

A dashboard management tool that exports QuickSight dashboards with their dependencies to asset bundles, stores backups in S3, and starts restoration jobs from selected backups or an S3 URI.

**Technologies:** Python · Streamlit · Boto3 · Amazon QuickSight · Amazon S3

**Engineering focus:** Cloud operations, AWS API integration, asynchronous job orchestration, and recovery tooling.

## Features

- Paginated dashboard discovery and an interactive backup/restore interface.
- Export-job polling, bundle download, and upload to S3.
- Import-job polling with progress messages and throttling handling.
- JSON configuration import, editing, and export.

## Limitations

- Local implementation reviewed; live export and restore were not run.
- Polling has a ten-minute local deadline and handles all documented terminal failure states; timing out does not cancel a remote job.
- S3 listings are paginated; backup keys use UTC timestamps and random suffixes to prevent same-day overwrites.
- Environment-specific configuration must be excluded from any public repository.

This is a prototype. Live AWS behavior and production readiness have not been verified.

## Local setup

Requires Python 3.10+ and AWS credentials configured for an account you are authorized to use. Use a sandbox account with synthetic resources for demonstrations.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

```sh
streamlit run app.py
```

Enter your own account, region, bucket, and prefix in the sidebar, or copy `config.example.json` to `config.json` and fill in your own values. Backup writes to S3; restore creates or changes QuickSight resources.

## Data handling

Local configuration, credentials, generated reports, spreadsheets, and asset bundles are excluded from this repository. Do not commit real account configuration, customer data, or secrets. AWS access uses configured local profiles or the SDK credential chain; no credentials are supplied.

## Validation

Run `python -m unittest -v` for ten offline tests covering failure states, deadline enforcement, throttling, pagination, input validation, and backup keys. No credentials or AWS requests are needed. Dependencies are not version-locked.

See [VALIDATION.md](VALIDATION.md) for the sandbox validation procedure and [the illustrated walkthrough](https://zayan15.github.io/demos.html) for a synthetic example.

AWS status references: [Import jobs](https://docs.aws.amazon.com/quicksight/latest/APIReference/API_DescribeAssetBundleImportJob.html) and [Export jobs](https://docs.aws.amazon.com/quicksight/latest/APIReference/API_DescribeAssetBundleExportJob.html).
