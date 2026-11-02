---
description: Set up or validate AWS CLI configuration
tags: [cloud, aws, setup, validation, project, gitignored]
---

You are helping the user set up or validate their AWS CLI configuration.

## Process

1. **Check if AWS CLI is installed**
   - Run `aws --version` to check installation
   - If not installed, install using: `sudo apt install awscli` or `pip3 install awscli --upgrade --user`

2. **Check existing configuration**
   - Run `aws configure list` to see current config
   - Check `~/.aws/credentials` and `~/.aws/config` files if they exist

3. **Validate configuration**
   - If credentials exist, test with: `aws sts get-caller-identity`
   - This will confirm the credentials are valid and show account info

4. **Configure if needed**
   - If not configured or user wants to update:
     - Run `aws configure` interactively OR
     - Ask user for: AWS Access Key ID, Secret Access Key, default region, output format
     - Offer to set up profiles if user has multiple AWS accounts

5. **Additional setup suggestions**
   - Suggest installing `aws-shell` for better CLI experience
   - Recommend setting up AWS SSO if applicable
   - Suggest configuring MFA if not already set up

## Output

Provide a summary showing:
- AWS CLI version
- Configured profiles
- Current default profile and region
- Validation status
- Any recommendations for improvement
