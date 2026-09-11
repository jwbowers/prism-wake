#!/usr/bin/env bash
# Sets up everything this needs inside AWS: the permissions the two programs
# run under, the two programs themselves, the public web address for the link,
# and the timer. At the end it prints the link to send your collaborator.
#
# You run this once, when nothing exists yet. Running it a second time stops
# with an error on the first thing it tries to create, because that thing is
# already there, and it creates nothing new. If the first run fails part way
# through, some pieces will exist and some will not. The error names the step
# that failed, and you delete what was made before trying again.
#
# To change the code after this has run, use `make package` and then
# `aws lambda update-function-code`.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)

# Your own values are in config.sh, which is not committed. Copy
# config.example.sh to config.sh and fill it in before running this.
if [ ! -f "$here/config.sh" ]; then
  echo "No config.sh found. Start from the example:" >&2
  echo "  cp config.example.sh config.sh && \$EDITOR config.sh" >&2
  exit 1
fi
# shellcheck source=config.example.sh
. "$here/config.sh"

for required in AWS_PROFILE REGION ACCOUNT INSTANCE_ID RSTUDIO_USER; do
  if [ -z "${!required:-}" ]; then
    echo "config.sh does not set $required" >&2
    exit 1
  fi
done

# This secret is the only thing standing between a stranger and the workspace,
# because the web address itself is open to anyone. Thirty-two random
# characters is far more than anyone can arrive at by guessing.
SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")

cd "$here"

# --- the permissions the programs run under -----------------------------
# Starting and stopping are allowed for this one workspace and no other. The
# permission to look up whether a machine is running cannot be narrowed to a
# single machine: AWS does not offer that, so the programs can read the state
# of any machine in the account. They can change only this one.
cat > /tmp/bw-trust.json <<'JSON'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}
JSON

cat > /tmp/bw-perms.json <<JSON
{"Version":"2012-10-17","Statement":[
 {"Effect":"Allow",
  "Action":["ec2:StartInstances","ec2:StopInstances"],
  "Resource":"arn:aws:ec2:${REGION}:${ACCOUNT}:instance/${INSTANCE_ID}"},
 {"Effect":"Allow","Action":"ec2:DescribeInstances","Resource":"*"},
 {"Effect":"Allow","Action":"cloudwatch:GetMetricStatistics","Resource":"*"},
 {"Effect":"Allow","Action":["logs:CreateLogGroup","logs:CreateLogStream",
  "logs:PutLogEvents"],"Resource":"arn:aws:logs:${REGION}:${ACCOUNT}:*"}]}
JSON

aws iam create-role --role-name "$ROLE" \
  --assume-role-policy-document file:///tmp/bw-trust.json >/dev/null
aws iam put-role-policy --role-name "$ROLE" \
  --policy-name "$POLICY_NAME" --policy-document file:///tmp/bw-perms.json

# New permissions take a few seconds to reach every part of AWS. Creating the
# programs too quickly fails with a complaint that the role cannot be used.
echo "waiting for the new permissions to take effect everywhere"
sleep 15

# --- the two programs ---------------------------------------------------
make package >/dev/null
ZIP="fileb://${here}/dist/prism-wake.zip"
# Recording the commit means you can ask AWS what is running rather than
# rebuilding zip files and comparing fingerprints. "-dirty" appears when the
# working tree had uncommitted changes, so the stamp can never claim the
# deployment came from a commit that does not contain it.
GIT_STAMP=$(git -C "$here" describe --always --dirty --abbrev=8 2>/dev/null || echo unknown)

ENV="Variables={INSTANCE_ID=${INSTANCE_ID},WAKE_SECRET=${SECRET},RSTUDIO_PORT=${RSTUDIO_PORT},RSTUDIO_USER=${RSTUDIO_USER},IDLE_CPU_PERCENT=${IDLE_CPU_PERCENT},IDLE_MINUTES=${IDLE_MINUTES},GIT_COMMIT=${GIT_STAMP}}"

for fn_handler in "${WEB_FN}:wake.web.lambda_handler" "${IDLE_FN}:wake.idle.lambda_handler"; do
  fn="${fn_handler%%:*}"; handler="${fn_handler##*:}"
  aws lambda create-function --function-name "$fn" --region "$REGION" \
    --runtime python3.13 --handler "$handler" \
    --role "arn:aws:iam::${ACCOUNT}:role/${ROLE}" \
    --zip-file "$ZIP" --timeout 30 --environment "$ENV" >/dev/null
done

# --- the public web address the link points at ---------------------------
# Amazon offers two ways to give a program a public web address. The simpler
# one, a Lambda function URL, refuses every request in this account with
# "access denied" even when configured exactly as Amazon documents, and the
# reason is not visible from the command line. So this uses the other way, an
# API Gateway, which is a separate Amazon service that takes web requests and
# hands them to a program. It works here, and the program itself is identical
# either way.
API=$(aws apigatewayv2 create-api --name "$API_NAME" --protocol-type HTTP \
  --target "arn:aws:lambda:${REGION}:${ACCOUNT}:function:${WEB_FN}" \
  --region "$REGION" --query ApiId --output text)
aws lambda add-permission --function-name "$WEB_FN" --region "$REGION" \
  --statement-id apigw-invoke --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:${REGION}:${ACCOUNT}:${API}/*" >/dev/null
URL=$(aws apigatewayv2 get-api --api-id "$API" --region "$REGION" \
  --query ApiEndpoint --output text)

# --- the timer that checks every fifteen minutes -------------------------
aws events put-rule --name "$RULE_NAME" --region "$REGION" \
  --schedule-expression "rate(15 minutes)" >/dev/null
aws lambda add-permission --function-name "$IDLE_FN" --region "$REGION" \
  --statement-id events-invoke --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:${REGION}:${ACCOUNT}:rule/${RULE_NAME}" >/dev/null
aws events put-targets --rule "$RULE_NAME" --region "$REGION" \
  --targets "Id=1,Arn=arn:aws:lambda:${REGION}:${ACCOUNT}:function:${IDLE_FN}" >/dev/null

echo
echo "Send your collaborator this one link, and nothing else:"
echo "  ${URL%/}?k=${SECRET}"
