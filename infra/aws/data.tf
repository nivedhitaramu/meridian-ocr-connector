resource "aws_kms_key" "main" {
  description             = "${local.name}: database, cache, uploads, secrets and logs"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy                  = data.aws_iam_policy_document.kms.json
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "kms" {
  statement {
    sid       = "Account"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }
  statement {
    sid       = "CloudWatchLogs"
    actions   = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
    resources = ["*"]
    principals {
      type        = "Service"
      identifiers = ["logs.${var.region}.amazonaws.com"]
    }
  }
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}"
  target_key_id = aws_kms_key.main.key_id
}

# Secrets are created empty. Put the values in once, outside Terraform, so they never enter its state:
#   aws secretsmanager put-secret-value --secret-id meridian-staging/llm-api-key --secret-string ...
resource "aws_secretsmanager_secret" "app" {
  for_each   = toset(["llm-api-key", "internal-api-token", "inbound-email-secret", "clerk-secret-key"])
  name       = "${local.name}/${each.key}"
  kms_key_id = aws_kms_key.main.arn
}

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "database_url" {
  name       = "${local.name}/database-url"
  kms_key_id = aws_kms_key.main.arn
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql+psycopg://meridian:${random_password.db.result}@${aws_db_instance.main.address}:5432/meridian?sslmode=require"
}

resource "aws_db_subnet_group" "main" {
  name       = local.name
  subnet_ids = [for s in aws_subnet.data : s.id]
}

resource "aws_db_parameter_group" "main" {
  name   = local.name
  family = "postgres17"
  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "-1" # statements can hold values; don't log them
  }
}

resource "aws_db_instance" "main" {
  identifier                   = local.name
  engine                       = "postgres"
  engine_version               = "17"
  instance_class               = var.db_instance_class
  allocated_storage            = 20
  max_allocated_storage        = 200
  storage_encrypted            = true
  kms_key_id                   = aws_kms_key.main.arn
  db_name                      = "meridian"
  username                     = "meridian"
  password                     = random_password.db.result
  multi_az                     = var.db_multi_az
  db_subnet_group_name         = aws_db_subnet_group.main.name
  vpc_security_group_ids       = [aws_security_group.data.id]
  parameter_group_name         = aws_db_parameter_group.main.name
  publicly_accessible          = false
  backup_retention_period      = var.environment == "production" ? 14 : 3
  deletion_protection          = var.environment == "production"
  skip_final_snapshot          = var.environment != "production"
  final_snapshot_identifier    = var.environment == "production" ? "${local.name}-final" : null
  performance_insights_enabled = false
  auto_minor_version_upgrade   = true
}

resource "aws_elasticache_subnet_group" "main" {
  name       = local.name
  subnet_ids = [for s in aws_subnet.data : s.id]
}

# Celery's broker. See README for why this stays Redis rather than SQS.
resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = local.name
  description                = "Celery broker"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  num_cache_clusters         = var.environment == "production" ? 2 : 1
  automatic_failover_enabled = var.environment == "production"
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.data.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  kms_key_id                 = aws_kms_key.main.arn
}

# Uploads wait here only until their job runs; a lifecycle rule removes anything a crash left behind.
resource "aws_s3_bucket" "uploads" {
  bucket_prefix = "${local.name}-uploads-"
  force_destroy = var.environment != "production"
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  rule {
    id     = "remove-leftovers"
    status = "Enabled"
    filter {}
    expiration {
      days = 1
    }
  }
}

resource "aws_s3_bucket_policy" "uploads_tls_only" {
  bucket = aws_s3_bucket.uploads.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "HttpsOnly"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.uploads.arn, "${aws_s3_bucket.uploads.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
}
