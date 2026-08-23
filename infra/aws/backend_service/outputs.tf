output "api_endpoint" {
  description = "Public HTTPS endpoint managed by API Gateway."
  value       = aws_apigatewayv2_api.airlock.api_endpoint
}

output "ecs_cluster_name" {
  description = "ECS cluster hosting the Airlock backend."
  value       = aws_ecs_cluster.airlock.name
}

output "ecs_service_name" {
  description = "ECS API service name used for deployments and monitoring."
  value       = aws_ecs_service.airlock.name
}

output "outbox_publisher_service_name" {
  description = "ECS service that publishes committed outbox events to SQS."
  value       = aws_ecs_service.outbox_publisher.name
}

output "scan_worker_service_name" {
  description = "ECS service that consumes and processes asynchronous scan messages."
  value       = aws_ecs_service.scan_worker.name
}

output "scan_queue_arn" {
  description = "Encrypted SQS queue carrying at-least-once scan messages."
  value       = aws_sqs_queue.scan.arn
}

output "scan_dead_letter_queue_arn" {
  description = "SQS dead-letter queue for exhausted scan deliveries."
  value       = aws_sqs_queue.scan_dlq.arn
}

output "task_definition_arn" {
  description = "API task definition that can also be used for a one-off Alembic migration command override."
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
  description = "API ECS execution role restricted to declared runtime secrets plus standard image/log access."
  value       = aws_iam_role.task_execution.arn
}

output "task_role_arn" {
  description = "API application task role. It intentionally has no SQS permissions."
  value       = aws_iam_role.task.arn
}

output "outbox_publisher_task_role_arn" {
  description = "Publisher runtime role restricted to SQS SendMessage on the scan queue."
  value       = aws_iam_role.outbox_publisher.arn
}

output "scan_worker_task_role_arn" {
  description = "Worker runtime role restricted to consuming and acknowledging scan messages."
  value       = aws_iam_role.scan_worker.arn
}
