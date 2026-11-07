output "url" {
  value = "https://${var.domain_name}"
}

output "ecr_repositories" {
  value = { for k, r in aws_ecr_repository.app : k => r.repository_url }
}

output "cluster" {
  value = aws_ecs_cluster.main.name
}

output "migrate_task_definition" {
  value = aws_ecs_task_definition.migrate.family
}

output "app_subnets" {
  value = [for s in aws_subnet.app : s.id]
}

output "app_security_group" {
  value = aws_security_group.app.id
}

output "secrets_to_fill" {
  description = "Put a value into each of these once, outside Terraform."
  value       = [for s in aws_secretsmanager_secret.app : s.name]
}
