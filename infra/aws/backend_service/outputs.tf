output "api_endpoint" {
  description = "Public HTTPS endpoint managed by API Gateway."
  value       = aws_apigatewayv2_api.airlock.api_endpoint
}

output "ecs_cluster_name" {
  description = "ECS cluster hosting the Airlock backend."
  value       = aws_ecs_cluster.airlock.name
}

output "ecs_service_name" {
  description = "ECS service name used for deployments and monitoring."
  value       = aws_ecs_service.airlock.name
}

output "task_definition_arn" {
  description = "Task definition that can also be used for a one-off Alembic migration command override."
  value       = aws_ecs_task_definition.airlock.arn
}

output "database_endpoint" {
  description = "Private RDS PostgreSQL endpoint."
  value       = aws_db_instance.airlock.address
  sensitive   = true
}

output "database_master_secret_arn" {
  description = "RDS-managed Secrets Manager secret containing the database username and password."
  value       = aws_db_instance.airlock.master_user_secret[0].secret_arn
  sensitive   = true
}

output "task_execution_role_arn" {
  description = "ECS execution role restricted to declared runtime secrets plus standard image/log access."
  value       = aws_iam_role.task_execution.arn
}

output "task_role_arn" {
  description = "Application task role. It intentionally has no AWS API permissions in this reference design."
  value       = aws_iam_role.task.arn
}
