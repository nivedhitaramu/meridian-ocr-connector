# Create this bucket and table once, by hand, before the first `terraform init`.
bucket         = "meridian-terraform-state-REPLACE"
key            = "staging/terraform.tfstate"
region         = "ap-south-1"
dynamodb_table = "meridian-terraform-locks"
encrypt        = true
