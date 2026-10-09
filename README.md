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
- Job polling lacks an overall deadline; restore handling needs coverage for all terminal failure states.
- S3 backup listing is not paginated, and repeated backups of the same dashboard on the same day use the same object key.
- Environment-specific configuration must be excluded from any public repository.

This is a prototype. Live AWS behavior and production readiness have not been verified.

## Local setup

Requires Python 3 and AWS credentials configured for an account you are authorized to use. Use a sandbox account with synthetic resources for demonstrations.

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

Python syntax was checked without executing application code. No AWS requests or deployment tests were run. The dependency list is not version-locked.
