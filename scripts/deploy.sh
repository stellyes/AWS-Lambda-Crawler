#!/bin/bash
set -e

# AWS Web Crawler Deployment Script (Python)
# Usage: ./deploy.sh [dev|staging|prod]

ENVIRONMENT=${1:-dev}
REGION="us-west-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "AWS Web Crawler Deployment (Python)"
echo "Environment: $ENVIRONMENT"
echo "Region: $REGION"
echo "============================================"

# Check prerequisites
check_prerequisites() {
    echo ""
    echo "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        echo "ERROR: AWS CLI is not installed"
        exit 1
    fi
    
    if ! command -v sam &> /dev/null; then
        echo "ERROR: AWS SAM CLI is not installed"
        exit 1
    fi
    
    if ! command -v docker &> /dev/null; then
        echo "ERROR: Docker is not installed (required for container build)"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        echo "ERROR: Python 3 is not installed"
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        echo "ERROR: AWS credentials not configured"
        exit 1
    fi
    
    # Check Docker is running
    if ! docker info &> /dev/null; then
        echo "ERROR: Docker is not running"
        exit 1
    fi
    
    echo "All prerequisites met!"
}

# Get AWS account ID
get_account_id() {
    aws sts get-caller-identity --query Account --output text
}

# Create ECR repository if it doesn't exist
create_ecr_repository() {
    local REPO_NAME="crawler-function-$ENVIRONMENT"
    
    echo ""
    echo "Checking ECR repository..."
    
    if ! aws ecr describe-repositories --repository-names "$REPO_NAME" --region "$REGION" &> /dev/null; then
        echo "Creating ECR repository: $REPO_NAME"
        aws ecr create-repository \
            --repository-name "$REPO_NAME" \
            --region "$REGION" \
            --image-scanning-configuration scanOnPush=true
    else
        echo "ECR repository already exists: $REPO_NAME"
    fi
}

# Build and push Docker image
build_and_push_image() {
    local ACCOUNT_ID=$(get_account_id)
    local REPO_NAME="crawler-function-$ENVIRONMENT"
    local ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$REPO_NAME"
    
    echo ""
    echo "Building and pushing Docker image..."
    
    # Login to ECR
    aws ecr get-login-password --region "$REGION" | \
        docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
    
    # Build image
    cd "$PROJECT_DIR"
    docker build -t "$REPO_NAME:latest" .
    
    # Tag image
    docker tag "$REPO_NAME:latest" "$ECR_URI:latest"
    
    # Push image
    docker push "$ECR_URI:latest"
    
    echo "Docker image pushed: $ECR_URI:latest"
}

# Build SAM application
build_sam() {
    echo ""
    echo "Building SAM application..."
    cd "$PROJECT_DIR/infrastructure"
    sam build --use-container
    echo "SAM build complete!"
}

# Deploy to AWS
deploy() {
    echo ""
    echo "Deploying to AWS..."
    cd "$PROJECT_DIR/infrastructure"
    
    sam deploy \
        --config-env "$ENVIRONMENT" \
        --region "$REGION" \
        --no-fail-on-empty-changeset
    
    echo "Deployment complete!"
}

# Print outputs
print_outputs() {
    echo ""
    echo "============================================"
    echo "Deployment Outputs"
    echo "============================================"
    
    STACK_NAME="aws-web-crawler-$ENVIRONMENT"
    
    echo ""
    echo "Queue URL:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='TaskQueueUrl'].OutputValue" \
        --output text
    
    echo ""
    echo "API Endpoint:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
        --output text
    
    echo ""
    echo "Results Bucket:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='ResultsBucketName'].OutputValue" \
        --output text
    
    echo ""
    echo "Secrets ARN:"
    aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='SecretsArn'].OutputValue" \
        --output text
}

# Post-deployment instructions
post_deploy_instructions() {
    echo ""
    echo "============================================"
    echo "Next Steps"
    echo "============================================"
    echo ""
    echo "1. Update your website credentials:"
    echo "   aws secretsmanager update-secret \\"
    echo "       --secret-id crawler/website-credentials-$ENVIRONMENT \\"
    echo "       --secret-string '{\"username\":\"YOUR_USERNAME\",\"password\":\"YOUR_PASSWORD\"}' \\"
    echo "       --region $REGION"
    echo ""
    echo "2. Submit a test task:"
    echo "   ./scripts/submit-task.sh"
    echo ""
    echo "3. View Lambda logs:"
    echo "   aws logs tail /aws/lambda/CrawlerFunction-$ENVIRONMENT --follow --region $REGION"
    echo ""
}

# Main execution
main() {
    check_prerequisites
    create_ecr_repository
    build_and_push_image
    build_sam
    deploy
    print_outputs
    post_deploy_instructions
}

main
