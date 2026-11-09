#!/bin/bash
# Deploy ProjectCompass to a k0s controller EC2.
#
# Handles everything: SG rules, S3 upload, extract, Docker build, admin setup.
# Idempotent — safe to run multiple times.
#
# Prerequisites:
#   - AWS CLI authenticated (aws login --profile <profile>)
#   - Docker + Docker Compose installed on the controller EC2
#   - k0s controller running with kubeconfig at /var/lib/k0s/pki/admin.conf
#
# Usage:
#   bash scripts/deploy_to_k0s.sh [INSTANCE_ID] [AWS_PROFILE]

set -euo pipefail

INSTANCE_ID="${1:-i-0779c89501f18d6b1}"
AWS_PROFILE="${2:-n1-console}"
AWS_REGION="us-east-1"
COMPASS_PORT=8080
S3_BUCKET="837134650544-eit-us-east-1-tfstate"
REMOTE_DIR="/home/ec2-user/compass"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

aws_cmd() { aws "$@" --profile "$AWS_PROFILE" --region "$AWS_REGION"; }
ssm_run() {
    local cmd_id
    cmd_id=$(aws_cmd ssm send-command \
        --instance-ids "$INSTANCE_ID" \
        --document-name AWS-RunShellScript \
        --timeout-seconds "${2:-120}" \
        --parameters commands="$1" \
        --output text --query 'Command.CommandId')
    sleep "${3:-10}"
    aws_cmd ssm get-command-invocation \
        --command-id "$cmd_id" --instance-id "$INSTANCE_ID" \
        --query '[Status,StandardOutputContent]' --output json
}

# ── Step 1: Ensure SG allows port 8080 ──────────────────────────────
echo "🔒 Ensuring port $COMPASS_PORT is open in security groups..."

SG_IDS=$(aws_cmd ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].SecurityGroups[*].GroupId' --output text)

PORT_OPEN=false
for sg in $SG_IDS; do
    EXISTING=$(aws_cmd ec2 describe-security-groups --group-ids "$sg" \
        --query "SecurityGroups[0].IpPermissions[?FromPort==\`$COMPASS_PORT\`] | length(@)" \
        --output text 2>/dev/null || echo 0)
    if [ "$EXISTING" != "0" ]; then
        PORT_OPEN=true
        break
    fi
done

if [ "$PORT_OPEN" = false ]; then
    # Find the SG with the most permissive rules (the one with port 8000 or similar)
    TARGET_SG=""
    for sg in $SG_IDS; do
        HAS_RULES=$(aws_cmd ec2 describe-security-groups --group-ids "$sg" \
            --query 'SecurityGroups[0].IpPermissions | length(@)' --output text)
        if [ "$HAS_RULES" != "0" ]; then
            TARGET_SG="$sg"
        fi
    done
    TARGET_SG="${TARGET_SG:-$(echo "$SG_IDS" | awk '{print $1}')}"

    echo "  Adding port $COMPASS_PORT to $TARGET_SG..."
    aws_cmd ec2 authorize-security-group-ingress \
        --group-id "$TARGET_SG" \
        --ip-permissions "IpProtocol=tcp,FromPort=$COMPASS_PORT,ToPort=$COMPASS_PORT,IpRanges=[{CidrIp=10.0.0.0/8,Description=VPN},{CidrIp=$(curl -s ifconfig.me)/32,Description=deployer}]" \
        --output text > /dev/null 2>&1 || echo "  (rule may already exist)"
    echo "  ✅ Port $COMPASS_PORT opened"
else
    echo "  ✅ Port $COMPASS_PORT already open"
fi

# ── Step 2: Package project ─────────────────────────────────────────
echo "📦 Packaging ProjectCompass..."
cd "$PROJECT_DIR"
tar czf /tmp/compass-deploy.tar.gz \
    --exclude='.git' --exclude='__pycache__' --exclude='.venv' \
    --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='tmp' \
    --exclude='*.db' --exclude='.DS_Store' --exclude='log/*' \
    --exclude='logs/*' --exclude='.idea' --exclude='.junie' \
    --exclude='.amazonq' --exclude='.mithril' --exclude='.github' \
    --exclude='tests' --exclude='.coverage' --exclude='uv.lock' \
    .
echo "  $(du -h /tmp/compass-deploy.tar.gz | cut -f1) packaged"

# ── Step 3: Upload via S3 ───────────────────────────────────────────
echo "📤 Uploading to S3..."
aws_cmd s3 cp /tmp/compass-deploy.tar.gz "s3://$S3_BUCKET/tmp/compass-deploy.tar.gz" --quiet
rm /tmp/compass-deploy.tar.gz
echo "  ✅ Uploaded"

# ── Step 4: Deploy on EC2 ───────────────────────────────────────────
echo "🚀 Deploying on EC2 $INSTANCE_ID..."

DEPLOY_COMMANDS='[
  "set -e",
  "aws s3 cp s3://'"$S3_BUCKET"'/tmp/compass-deploy.tar.gz /tmp/compass-deploy.tar.gz --region '"$AWS_REGION"' --quiet",
  "rm -rf '"$REMOTE_DIR"'",
  "mkdir -p '"$REMOTE_DIR"'",
  "cd '"$REMOTE_DIR"' && tar xzf /tmp/compass-deploy.tar.gz",
  "rm /tmp/compass-deploy.tar.gz",
  "cd '"$REMOTE_DIR"' && docker compose -f docker-compose.yml up -d --build --force-recreate projectcompass 2>&1 | tail -5",
  "sleep 12",
  "curl -s http://localhost:'"$COMPASS_PORT"'/health || echo HEALTH_FAIL",
  "curl -s -X POST http://localhost:'"$COMPASS_PORT"'/setup/create-admin -d \"username=admin&password=compass2026&password_confirm=compass2026\" -o /dev/null -w \"Setup: %{http_code}\"",
  "echo",
  "echo DEPLOY_DONE"
]'

RESULT=$(ssm_run "$DEPLOY_COMMANDS" 300 90)
STATUS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())[0])")
if [ "$STATUS" != "Success" ]; then
    echo "❌ Deploy failed"
    echo "$RESULT" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())[1])"
    exit 1
fi

# ── Step 5: Clean S3 ────────────────────────────────────────────────
aws_cmd s3 rm "s3://$S3_BUCKET/tmp/compass-deploy.tar.gz" --quiet 2>/dev/null || true

# ── Step 6: Get EC2 IP and print URL ────────────────────────────────
IP=$(aws_cmd ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' --output text)

echo ""
echo "✅ ProjectCompass deployed"
echo "   URL:   http://$IP:$COMPASS_PORT"
echo "   Login: admin / compass2026"
echo "   Health: http://$IP:$COMPASS_PORT/health"
