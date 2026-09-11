# Copy this to config.sh and fill in your own values. config.sh is not
# committed, so your account number and machine never leave your computer.
#
#     cp config.example.sh config.sh
#     $EDITOR config.sh
#     ./deploy.sh

# Which AWS profile and region the workspace lives in.
export AWS_PROFILE=default
export REGION=us-east-2

# Your twelve-digit AWS account number. Find it with:
#     aws sts get-caller-identity --query Account --output text
export ACCOUNT=000000000000

# The machine this link wakes. Find it with:
#     aws ec2 describe-instances --region "$REGION" \
#       --filters Name=tag:Name,Values=YOUR-WORKSPACE-NAME \
#       --query 'Reservations[].Instances[].InstanceId' --output text
export INSTANCE_ID=i-0000000000000000

# The Linux account your collaborator signs in to RStudio with, and the port
# RStudio serves on. The account must be one RStudio will accept: by default
# that means a member of whatever group `auth-required-user-group` names in
# /etc/rstudio/rserver.conf.
export RSTUDIO_USER=collaborator
export RSTUDIO_PORT=8787

# When the timer puts the workspace to sleep: every five-minute processor
# reading in the last IDLE_MINUTES must be below IDLE_CPU_PERCENT.
export IDLE_CPU_PERCENT=5
export IDLE_MINUTES=120

# What to call things in AWS. Change these if you run more than one.
export ROLE=bristol-wake-role
export WEB_FN=bristol-wake-web
export IDLE_FN=bristol-wake-idle
export API_NAME=bristol-wake
