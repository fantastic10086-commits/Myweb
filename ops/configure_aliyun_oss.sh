#!/bin/bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this configuration as root." >&2
    exit 1
fi

OSSUTIL_BIN=/usr/local/bin/ossutil2
CONFIG_FILE=/root/.ossutilconfig-pi-manager
BUCKET=pi-manager-backup
REGION=cn-hongkong
ENDPOINT=https://oss-cn-hongkong-internal.aliyuncs.com

if [ ! -x "$OSSUTIL_BIN" ]; then
    echo "Alibaba ossutil 2.0 is not installed." >&2
    exit 1
fi

printf 'Alibaba Cloud AccessKey ID: '
IFS= read -r ACCESS_KEY_ID
printf 'Alibaba Cloud AccessKey Secret (input is hidden): '
IFS= read -rs ACCESS_KEY_SECRET
printf '\n'

if [ -z "$ACCESS_KEY_ID" ] || [ -z "$ACCESS_KEY_SECRET" ]; then
    echo "AccessKey ID and Secret are required." >&2
    exit 1
fi

# Remove carriage returns and a pair of surrounding CSV quotes, if present.
ACCESS_KEY_ID="${ACCESS_KEY_ID//$'\r'/}"
ACCESS_KEY_SECRET="${ACCESS_KEY_SECRET//$'\r'/}"
if [[ "$ACCESS_KEY_ID" == \"*\" ]]; then
    ACCESS_KEY_ID="${ACCESS_KEY_ID:1:${#ACCESS_KEY_ID}-2}"
fi
if [[ "$ACCESS_KEY_SECRET" == \"*\" ]]; then
    ACCESS_KEY_SECRET="${ACCESS_KEY_SECRET:1:${#ACCESS_KEY_SECRET}-2}"
fi

umask 077
TMP_CONFIG="$(mktemp /root/.ossutilconfig-pi-manager.XXXXXX)"
trap 'rm -f "$TMP_CONFIG"' EXIT

{
    printf '[default]\n'
    printf 'mode = AK\n'
    printf 'accessKeyID = %s\n' "$ACCESS_KEY_ID"
    printf 'accessKeySecret = %s\n' "$ACCESS_KEY_SECRET"
    printf 'region = %s\n' "$REGION"
    printf 'endpoint = %s\n' "$ENDPOINT"
    printf 'signVersion = v4\n'
    printf 'language = EN\n'
} >"$TMP_CONFIG"

chmod 0600 "$TMP_CONFIG"
unset ACCESS_KEY_ID ACCESS_KEY_SECRET

echo "Testing access to the private OSS bucket..."
if ! "$OSSUTIL_BIN" ls "oss://${BUCKET}" --config-file "$TMP_CONFIG" --limited-num 1 >/dev/null; then
    echo "The AccessKey test failed. No credentials were saved; run this setup again." >&2
    exit 1
fi

mv "$TMP_CONFIG" "$CONFIG_FILE"
trap - EXIT
echo "Alibaba OSS backup access is configured successfully."
