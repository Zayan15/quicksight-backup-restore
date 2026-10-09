import os
import json
import streamlit as st
import boto3
import uuid
import time
import io
import re
import requests
from datetime import datetime
from urllib.parse import urlparse

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULT_CONFIG = {
    'account_id': '',
    'region': 'us-west-2',
    's3_bucket': '',
    's3_prefix': 'reports-latest/',
}

def load_config_from_file(path):
    """Load config from a JSON file path. Returns dict or None on failure."""
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return {k: data.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG}
    except Exception:
        return None

def load_config_from_upload(uploaded_file):
    """Load config from a Streamlit UploadedFile. Returns dict or None."""
    try:
        data = json.load(uploaded_file)
        return {k: data.get(k, DEFAULT_CONFIG[k]) for k in DEFAULT_CONFIG}
    except Exception:
        return None

def save_config_to_file(cfg, path):
    """Persist config dict to JSON file."""
    with open(path, 'w') as f:
        json.dump(cfg, f, indent=2)

def init_config():
    """Initialise session_state config once per session."""
    if 'cfg' not in st.session_state:
        cfg = load_config_from_file(CONFIG_FILE)
        if cfg is None:
            cfg = DEFAULT_CONFIG.copy()
        st.session_state.cfg = cfg

def cfg():
    return st.session_state.cfg

st.set_page_config(
    page_title="QuickSight Asset Manager",
    page_icon="📊",
    layout="wide"
)

init_config()

def get_clients():
    c = cfg()
    return {
        'quicksight': boto3.client('quicksight', region_name=c['region']),
        's3': boto3.client('s3', region_name=c['region']),
    }

def sanitize_name(name):
    return re.sub(r'[\\^`{}]', '_', name)

def list_dashboards():
    clients = get_clients()
    account_id = cfg()['account_id']
    dashboards = []
    try:
        paginator = clients['quicksight'].get_paginator('list_dashboards')
        for page in paginator.paginate(AwsAccountId=account_id):
            dashboards.extend(page.get('DashboardSummaryList', []))
    except Exception as e:
        st.error(f"Error listing dashboards: {e}")
    return dashboards

def list_s3_backups():
    clients = get_clients()
    c = cfg()
    backups = []
    try:
        response = clients['s3'].list_objects_v2(Bucket=c['s3_bucket'], Prefix=c['s3_prefix'])
        for obj in response.get('Contents', []):
            if obj['Key'].endswith('.qs'):
                backups.append({
                    'key': obj['Key'],
                    'name': obj['Key'].replace(c['s3_prefix'], '').replace('.qs', ''),
                    'size': obj['Size'],
                    'modified': obj['LastModified']
                })
    except Exception as e:
        st.error(f"Error listing S3 backups: {e}")
    return backups

def export_dashboard(dashboard_id, dashboard_name):
    clients = get_clients()
    c = cfg()
    job_id = str(uuid.uuid4())
    dashboard_arn = f"arn:aws:quicksight:{c['region']}:{c['account_id']}:dashboard/{dashboard_id}"
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("Starting export job...")
        clients['quicksight'].start_asset_bundle_export_job(
            AwsAccountId=c['account_id'],
            AssetBundleExportJobId=job_id,
            ResourceArns=[dashboard_arn],
            IncludeAllDependencies=True,
            ExportFormat='QUICKSIGHT_JSON'
        )
        
        progress_bar.progress(25)
        status_text.text("Waiting for export to complete...")
        
        wait_time = 5
        max_wait = 60
        while True:
            try:
                response = clients['quicksight'].describe_asset_bundle_export_job(
                    AwsAccountId=c['account_id'],
                    AssetBundleExportJobId=job_id
                )
                
                status = response['JobStatus']
                if status == 'FAILED':
                    st.error("Export job failed!")
                    return False
                elif status in ['COMPLETED', 'SUCCESSFUL']:
                    break
                    
                status_text.text(f"Export status: {status}... waiting {wait_time}s")
                time.sleep(wait_time)
                wait_time = min(wait_time * 1.2, max_wait)
                
            except Exception as api_error:
                if 'ThrottlingException' in str(api_error):
                    status_text.text(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    wait_time = min(wait_time * 2, max_wait)
                else:
                    raise api_error
        
        progress_bar.progress(50)
        status_text.text("Downloading asset bundle...")
        
        url = response.get('DownloadUrl')
        if not url:
            st.error("No download URL available")
            return False
        
        r = requests.get(url)
        r.raise_for_status()
        
        progress_bar.progress(75)
        status_text.text("Uploading to S3...")
        
        sanitized_name = sanitize_name(dashboard_name)
        timestamp = datetime.now().strftime('%Y%m%d')
        s3_key = f"{c['s3_prefix']}{sanitized_name}_{timestamp}.qs"
        
        clients['s3'].upload_fileobj(
            io.BytesIO(r.content),
            c['s3_bucket'],
            s3_key
        )
        
        progress_bar.progress(100)
        status_text.text("✅ Export completed successfully!")
        return True
        
    except Exception as e:
        st.error(f"Export failed: {e}")
        return False

def restore_asset(s3_uri):
    clients = get_clients()
    c = cfg()
    job_id = str(int(time.time()))
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    try:
        status_text.text("Starting restoration job...")
        clients['quicksight'].start_asset_bundle_import_job(
            AwsAccountId=c['account_id'],
            AssetBundleImportJobId=job_id,
            AssetBundleImportSource={'S3Uri': s3_uri}
        )
        
        progress_bar.progress(25)
        status_text.text("Waiting for restoration to complete...")
        
        wait_time = 5
        max_wait = 60
        while True:
            try:
                response = clients['quicksight'].describe_asset_bundle_import_job(
                    AwsAccountId=c['account_id'],
                    AssetBundleImportJobId=job_id
                )
                
                status = response['JobStatus']
                if status == 'FAILED':
                    st.error("Restoration job failed!")
                    if 'Errors' in response:
                        for error in response['Errors']:
                            st.error(f"Error: {error}")
                    return False
                elif status == 'SUCCESSFUL':
                    break
                elif status in ['QUEUED', 'IN_PROGRESS']:
                    status_text.text(f"Job status: {status}... waiting {wait_time}s")
                    time.sleep(wait_time)
                    wait_time = min(wait_time * 1.5, max_wait)
                    
            except Exception as api_error:
                if 'ThrottlingException' in str(api_error):
                    status_text.text(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    wait_time = min(wait_time * 2, max_wait)
                else:
                    raise api_error
            
        progress_bar.progress(100)
        status_text.text("✅ Restoration completed successfully!")
        return True
        
    except Exception as e:
        st.error(f"Restoration failed: {e}")
        return False

# Main UI
st.title("📊 QuickSight Asset Manager")
st.markdown("Backup and restore QuickSight dashboards with ease")

# Sidebar for configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    # --- Load from file upload ---
    uploaded = st.file_uploader("Load config from JSON file", type="json", key="config_upload")
    if uploaded is not None:
        loaded = load_config_from_upload(uploaded)
        if loaded:
            st.session_state.cfg = loaded
            st.success("Config loaded from file!")
        else:
            st.error("Invalid config file.")

    st.divider()

    # --- Manual fields (pre-filled from current config) ---
    c = cfg()
    account_id  = st.text_input("AWS Account ID", value=c['account_id'])
    region      = st.text_input("AWS Region",      value=c['region'])
    s3_bucket   = st.text_input("S3 Bucket",       value=c['s3_bucket'])
    s3_prefix   = st.text_input("S3 Prefix",       value=c['s3_prefix'])

    col_apply, col_save = st.columns(2)

    with col_apply:
        if st.button("Apply", use_container_width=True):
            st.session_state.cfg = {
                'account_id': account_id,
                'region': region,
                's3_bucket': s3_bucket,
                's3_prefix': s3_prefix,
            }
            st.success("Configuration applied!")

    with col_save:
        if st.button("Save to file", use_container_width=True):
            new_cfg = {
                'account_id': account_id,
                'region': region,
                's3_bucket': s3_bucket,
                's3_prefix': s3_prefix,
            }
            st.session_state.cfg = new_cfg
            save_config_to_file(new_cfg, CONFIG_FILE)
            st.success(f"Saved to config.json!")

    st.divider()
    st.download_button(
        "⬇️ Download config.json",
        data=json.dumps(cfg(), indent=2),
        file_name="config.json",
        mime="application/json",
        use_container_width=True,
    )

# Main tabs
tab1, tab2 = st.tabs(["📤 Backup Dashboards", "📥 Restore Assets"])

with tab1:
    st.header("Backup Dashboards")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if st.button("🔄 Refresh Dashboard List"):
            st.cache_resource.clear()
    
    dashboards = list_dashboards()
    
    if dashboards:
        st.subheader(f"Found {len(dashboards)} dashboards")
        
        for dashboard in dashboards:
            with st.expander(f"📊 {dashboard['Name']}"):
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(f"**ID:** {dashboard['DashboardId']}")
                    st.write(f"**Created:** {dashboard.get('CreatedTime', 'N/A')}")
                
                with col2:
                    if st.button(f"Backup", key=f"backup_{dashboard['DashboardId']}"):
                        with st.spinner("Exporting dashboard..."):
                            success = export_dashboard(dashboard['DashboardId'], dashboard['Name'])
                            if success:
                                st.success("Dashboard backed up successfully!")
                                st.balloons()
    else:
        st.info("No dashboards found or unable to connect to QuickSight")

with tab2:
    st.header("Restore Assets")
    
    # Option 1: Restore from S3 backups
    st.subheader("📁 Restore from S3 Backups")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        if st.button("🔄 Refresh Backup List"):
            st.cache_resource.clear()
    
    backups = list_s3_backups()
    
    if backups:
        selected_backup = st.selectbox(
            "Select backup to restore:",
            options=backups,
            format_func=lambda x: f"{x['name']} ({x['modified'].strftime('%Y-%m-%d %H:%M')})"
        )
        
        if selected_backup and st.button("🔄 Restore Selected Backup"):
            s3_uri = f"s3://{cfg()['s3_bucket']}/{selected_backup['key']}"
            with st.spinner("Restoring asset..."):
                success = restore_asset(s3_uri)
                if success:
                    st.success("Asset restored successfully!")
                    st.balloons()
    
    st.divider()
    
    # Option 2: Restore from custom S3 URI
    st.subheader("🔗 Restore from Custom S3 URI")
    
    s3_uri = st.text_input(
        "S3 URI:",
        placeholder="s3://bucket-name/path/to/asset.qs",
        help="Enter the full S3 URI of the asset bundle to restore"
    )
    
    if s3_uri and st.button("🔄 Restore from URI"):
        try:
            parsed = urlparse(s3_uri)
            if parsed.scheme != 's3':
                st.error("Invalid S3 URI format")
            else:
                with st.spinner("Restoring asset..."):
                    success = restore_asset(s3_uri)
                    if success:
                        st.success("Asset restored successfully!")
                        st.balloons()
        except Exception as e:
            st.error(f"Invalid S3 URI: {e}")

# Footer
st.markdown("---")
st.markdown("💡 **Tip:** Make sure your AWS credentials are configured and you have the necessary QuickSight permissions.")