# #35: alarms for failures, latency, the queue and the fallback rate. All go to one SNS topic.

resource "aws_sns_topic" "alerts" {
  name              = "${local.name}-alerts"
  kms_master_key_id = aws_kms_key.main.id
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

locals {
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${local.name}-api-5xx"
  alarm_description   = "The API returned server errors."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix, TargetGroup = aws_lb_target_group.service["api"].arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${local.name}-api-latency-p95"
  alarm_description   = "API p95 response time above 5 seconds. /v1/extract runs OCR inline, so allow for that."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "TargetResponseTime"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix, TargetGroup = aws_lb_target_group.service["api"].arn_suffix }
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 3
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_metric_alarm" "worker_down" {
  for_each            = toset(["worker", "delivery"])
  alarm_name          = "${local.name}-${each.key}-down"
  alarm_description   = "No ${each.key} tasks are running, so jobs or deliveries wait."
  namespace           = "ECS/ContainerInsights"
  metric_name         = "RunningTaskCount"
  dimensions          = { ClusterName = aws_ecs_cluster.main.name, ServiceName = each.key }
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 5
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = local.alarm_actions
}

# The worker logs one JSON line per finished job: {"stage": "job.end", "outcome": ...}. These filters count them.
resource "aws_cloudwatch_log_metric_filter" "job_outcome" {
  for_each       = toset(["failed", "manual_review", "succeeded"])
  name           = "${local.name}-jobs-${each.key}"
  log_group_name = aws_cloudwatch_log_group.app["worker"].name
  pattern        = "{ $.stage = \"job.end\" && $.outcome = \"${each.key}\" }"
  metric_transformation {
    name          = "Jobs_${each.key}"
    namespace     = "Meridian/${var.environment}"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "job_failures" {
  alarm_name          = "${local.name}-job-failures"
  alarm_description   = "Jobs are failing. Manual review is expected; failures aren't."
  namespace           = "Meridian/${var.environment}"
  metric_name         = "Jobs_failed"
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  threshold           = 3
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

# The pipeline logs {"stage": "request.end", ...} and spans record whether the vision fallback ran.
resource "aws_cloudwatch_log_metric_filter" "fallback" {
  name           = "${local.name}-vision-fallback"
  log_group_name = aws_cloudwatch_log_group.app["worker"].name
  pattern        = "{ $.stage = \"ocr\" && $.fallback IS TRUE }"
  metric_transformation {
    name          = "VisionFallback"
    namespace     = "Meridian/${var.environment}"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "fallback_rate" {
  alarm_name          = "${local.name}-fallback-high"
  alarm_description   = "Many scans need the vision fallback, which costs more and often ends in manual review."
  namespace           = "Meridian/${var.environment}"
  metric_name         = "VisionFallback"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 20
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = local.alarm_actions
}

# Queue depth: Redis doesn't publish Celery's queue length, so this uses the broker's memory as a proxy.
resource "aws_cloudwatch_metric_alarm" "queue_backlog" {
  alarm_name          = "${local.name}-queue-backlog"
  alarm_description   = "Broker memory is high, which usually means jobs are piling up."
  namespace           = "AWS/ElastiCache"
  metric_name         = "DatabaseMemoryUsagePercentage"
  dimensions          = { ReplicationGroupId = aws_elasticache_replication_group.main.id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 60
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = local.alarm_actions
}

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", width = 12, height = 6,
        properties = {
          title = "Jobs", region = var.region, stat = "Sum", period = 300,
          metrics = [for o in ["succeeded", "manual_review", "failed"] : ["Meridian/${var.environment}", "Jobs_${o}"]]
        }
      },
      {
        type = "metric", width = 12, height = 6,
        properties = {
          title = "API latency p95 and 5xx", region = var.region, period = 300,
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", "LoadBalancer", aws_lb.main.arn_suffix, "TargetGroup", aws_lb_target_group.service["api"].arn_suffix, { stat = "p95" }],
            [".", "HTTPCode_Target_5XX_Count", ".", ".", ".", ".", { stat = "Sum", yAxis = "right" }],
          ]
        }
      },
      {
        type = "metric", width = 12, height = 6,
        properties = {
          title = "Fallback and broker memory", region = var.region, period = 300,
          metrics = [
            ["Meridian/${var.environment}", "VisionFallback", { stat = "Sum" }],
            ["AWS/ElastiCache", "DatabaseMemoryUsagePercentage", "ReplicationGroupId", aws_elasticache_replication_group.main.id, { yAxis = "right" }],
          ]
        }
      },
    ]
  })
}
