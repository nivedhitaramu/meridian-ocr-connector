terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State lives in S3 with a lock table. Pass the bucket per environment:
  #   terraform init -backend-config=envs/staging.backend.hcl
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "meridian-intelligence"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# CloudFront's certificate and WAF must be in us-east-1.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
