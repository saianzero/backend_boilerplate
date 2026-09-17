#!/bin/bash
# AWS Elastic Beanstalk post-deploy hook (optional).
# Writes a GCP Workload Identity Federation credential file so Vertex AI can
# be called from EC2 without a service-account key. Replace the placeholders
# (<GCP_PROJECT_NUMBER>, <POOL_ID>, <PROVIDER_ID>, <SERVICE_ACCOUNT_EMAIL>)
# or delete this directory if you do not deploy on Elastic Beanstalk.
set -e

if [ -f /etc/gcp/gcp_wif_credentials.json ]; then
  echo "GCP WIF credentials already exist, skipping."
  exit 0
fi

echo "Writing GCP WIF credential config..."

mkdir -p /etc/gcp

cat > /tmp/gcp_wif_credentials.json << 'CREDJSON'
{
  "universe_domain": "googleapis.com",
  "type": "external_account",
  "audience": "//iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/providers/<PROVIDER_ID>",
  "subject_token_type": "urn:ietf:params:aws:token-type:aws4_request",
  "token_url": "https://sts.googleapis.com/v1/token",
  "credential_source": {
    "environment_id": "aws1",
    "region_url": "http://169.254.169.254/latest/meta-data/placement/availability-zone",
    "url": "http://169.254.169.254/latest/meta-data/iam/security-credentials",
    "regional_cred_verification_url": "https://sts.{region}.amazonaws.com?Action=GetCallerIdentity&Version=2011-06-15",
    "imdsv2_session_token_url": "http://169.254.169.254/latest/api/token"
  },
  "service_account_impersonation_url": "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/<SERVICE_ACCOUNT_EMAIL>:generateAccessToken",
  "service_account_impersonation": {
    "token_lifetime_seconds": 3600
  }
}
CREDJSON

mv /tmp/gcp_wif_credentials.json /etc/gcp/gcp_wif_credentials.json
chmod 640 /etc/gcp/gcp_wif_credentials.json
chown root:webapp /etc/gcp/gcp_wif_credentials.json

echo "GCP WIF credentials setup complete."