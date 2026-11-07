resource "aws_ecr_repository" "app" {
  for_each             = toset(["api", "web"])
  name                 = "meridian/${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.main.arn
  }
}

resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "app" {
  for_each          = toset(["api", "web", "worker", "delivery", "migrate", "otel"])
  name              = "/meridian/${var.environment}/${each.key}"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

# ------------------------------------------------------------------ roles
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Pulls images, writes logs and reads this environment's secrets. Nothing else.
resource "aws_iam_role" "execution" {
  name               = "${local.name}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "execution_secrets" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = concat([for s in aws_secretsmanager_secret.app : s.arn], [aws_secretsmanager_secret.database_url.arn])
      },
      { Effect = "Allow", Action = ["kms:Decrypt"], Resource = [aws_kms_key.main.arn] },
    ]
  })
}

# What the running code may do: read and write uploads, and send traces and metrics.
resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["${aws_s3_bucket.uploads.arn}/*"]
      },
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = [aws_s3_bucket.uploads.arn] },
      { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = [aws_kms_key.main.arn] },
      {
        Effect   = "Allow"
        Action   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "cloudwatch:PutMetricData", "logs:PutLogEvents", "logs:CreateLogStream"]
        Resource = ["*"]
      },
    ]
  })
}

# ------------------------------------------------------------------ tasks
locals {
  api_image = "${aws_ecr_repository.app["api"].repository_url}:${var.image_tag}"
  web_image = "${aws_ecr_repository.app["web"].repository_url}:${var.image_tag}"
  redis_url = "rediss://${aws_elasticache_replication_group.main.primary_endpoint_address}:6379/0?ssl_cert_reqs=required"

  environment = [
    { name = "LLM_PROVIDER", value = "openai_compatible" },
    { name = "LLM_BASE_URL", value = var.llm_base_url },
    { name = "LLM_MODEL", value = var.llm_model },
    { name = "CLERK_ISSUER", value = var.clerk_issuer },
    { name = "CLERK_AUTHORIZED_PARTIES", value = "https://${var.domain_name}" },
    { name = "ALLOWED_ORIGINS", value = "https://${var.domain_name}" },
    { name = "REDIS_URL", value = local.redis_url },
    { name = "STORAGE_BACKEND", value = "s3" },
    { name = "S3_BUCKET", value = aws_s3_bucket.uploads.bucket },
    { name = "AWS_REGION", value = var.region },
    { name = "OTEL_CONSOLE_EXPORT", value = "0" },
    { name = "OTEL_EXPORTER_OTLP_ENDPOINT", value = "http://localhost:4318/v1/traces" },
    { name = "MAX_EML_ATTACHMENTS", value = "4" },
  ]
  secrets = [
    { name = "DATABASE_URL", valueFrom = aws_secretsmanager_secret.database_url.arn },
    { name = "LLM_API_KEY", valueFrom = aws_secretsmanager_secret.app["llm-api-key"].arn },
    { name = "INTERNAL_API_TOKEN", valueFrom = aws_secretsmanager_secret.app["internal-api-token"].arn },
    { name = "INBOUND_EMAIL_SECRET", valueFrom = aws_secretsmanager_secret.app["inbound-email-secret"].arn },
  ]

  web_secrets = [{ name = "CLERK_SECRET_KEY", valueFrom = aws_secretsmanager_secret.app["clerk-secret-key"].arn }]

  # Collects OpenTelemetry traces next to each task and sends them to X-Ray and CloudWatch (#35).
  otel_sidecar = {
    name      = "otel"
    image     = "public.ecr.aws/aws-observability/aws-otel-collector:v0.43.1"
    essential = false
    command   = ["--config=/etc/ecs/ecs-default-config.yaml"]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["otel"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "otel"
      }
    }
  }

  services = {
    api = {
      image   = local.api_image
      command = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
      port    = 8000
      cpu     = 1024
      memory  = 2048
      count   = var.api_count
      subnets = [for s in aws_subnet.app : s.id]
      sg      = aws_security_group.app.id
    }
    worker = {
      image   = local.api_image
      command = ["celery", "-A", "app.worker.celery_app", "worker", "-Q", "celery", "--loglevel=info", "--concurrency=2"]
      port    = null
      cpu     = 2048
      memory  = 4096
      count   = var.worker_count
      subnets = [for s in aws_subnet.app : s.id]
      sg      = aws_security_group.app.id
    }
    delivery = {
      image   = local.api_image
      command = ["celery", "-A", "app.worker.celery_app", "worker", "-Q", "deliveries", "--beat", "--loglevel=info", "--concurrency=2", "--schedule=/tmp/celerybeat-schedule"]
      port    = null
      cpu     = 512
      memory  = 1024
      count   = 1 # also runs the nightly schedule, so keep exactly one
      subnets = [for s in aws_subnet.delivery : s.id]
      sg      = aws_security_group.delivery.id
    }
    web = {
      image   = local.web_image
      command = ["node", "server.js"]
      port    = 3000
      cpu     = 512
      memory  = 1024
      count   = var.web_count
      subnets = [for s in aws_subnet.app : s.id]
      sg      = aws_security_group.app.id
    }
  }
}

resource "aws_ecs_task_definition" "service" {
  for_each                 = local.services
  family                   = "${local.name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }
  container_definitions = jsonencode(concat([
    {
      name                   = each.key
      image                  = each.value.image
      command                = each.value.command
      essential              = true
      readonlyRootFilesystem = false
      environment            = each.key == "web" ? [{ name = "API_URL", value = "https://${var.domain_name}" }] : local.environment
      secrets                = each.key == "web" ? local.web_secrets : local.secrets
      portMappings           = each.value.port == null ? [] : [{ containerPort = each.value.port, protocol = "tcp" }]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app[each.key].name
          awslogs-region        = var.region
          awslogs-stream-prefix = each.key
        }
      }
    }
  ], each.key == "web" ? [] : [local.otel_sidecar]))
}

resource "aws_ecs_service" "service" {
  for_each               = local.services
  name                   = each.key
  cluster                = aws_ecs_cluster.main.id
  task_definition        = aws_ecs_task_definition.service[each.key].arn
  desired_count          = each.value.count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets          = each.value.subnets
    security_groups  = [each.value.sg]
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  dynamic "load_balancer" {
    for_each = each.value.port == null ? [] : [1]
    content {
      target_group_arn = aws_lb_target_group.service[each.key].arn
      container_name   = each.key
      container_port   = each.value.port
    }
  }
}

# One-off task the pipeline runs before each deploy: `alembic upgrade head`.
resource "aws_ecs_task_definition" "migrate" {
  family                   = "${local.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name        = "migrate"
    image       = local.api_image
    essential   = true
    command     = ["alembic", "upgrade", "head"]
    environment = local.environment
    secrets     = local.secrets
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.app["migrate"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "migrate"
      }
    }
  }])
}
