variable "outbox_publisher_desired_count" {
  description = "Number of transactional-outbox publisher tasks."
  type        = number
  default     = 1

  validation {
    condition     = var.outbox_publisher_desired_count >= 1 && var.outbox_publisher_desired_count <= 10
    error_message = "Outbox publisher desired count must be between 1 and 10."
  }
}

variable "scan_worker_desired_count" {
  description = "Number of horizontally scalable asynchronous scan worker tasks."
  type        = number
  default     = 2

  validation {
    condition     = var.scan_worker_desired_count >= 1 && var.scan_worker_desired_count <= 20
    error_message = "Scan worker desired count must be between 1 and 20."
  }
}

variable "scan_visibility_timeout_seconds" {
  description = "SQS visibility timeout and worker claim lease for one scan attempt."
  type        = number
  default     = 120

  validation {
    condition = (
      var.scan_visibility_timeout_seconds >= 10 &&
      var.scan_visibility_timeout_seconds <= 43200
    )
    error_message = "Scan visibility timeout must be between 10 and 43200 seconds."
  }
}

variable "scan_queue_max_receive_count" {
  description = "Failed deliveries allowed before SQS redrives a scan message to the DLQ."
  type        = number
  default     = 5

  validation {
    condition     = var.scan_queue_max_receive_count >= 2 && var.scan_queue_max_receive_count <= 20
    error_message = "Scan queue max receive count must be between 2 and 20."
  }
}

# -----------------------------------------------------------------------------
# Durable at-least-once scan transport
# -----------------------------------------------------------------------------

resource "aws_sqs_queue" "scan_dlq" {
  name                      = "${local.name_prefix}-scan-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "scan" {
  name                       = "${local.name_prefix}-scan"
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = var.scan_visibility_timeout_seconds
  message_retention_seconds  = 345600
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.scan_dlq.arn
    maxReceiveCount     = var.scan_queue_max_receive_count
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "scan_dlq" {
  queue_url = aws_sqs_queue.scan_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.scan.arn]
  })
}

# -----------------------------------------------------------------------------
# Separate execution identity: async tasks need only the database runtime secret.
# -----------------------------------------------------------------------------

resource "aws_iam_role" "async_task_execution" {
  name               = "${local.name_prefix}-async-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "async_task_execution" {
  role       = aws_iam_role.async_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "async_task_execution_secrets" {
  statement {
    sid       = "ReadDatabaseRuntimeSecret"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.airlock.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "async_task_execution_secrets" {
  name   = "read-airlock-database-secret"
  role   = aws_iam_role.async_task_execution.id
  policy = data.aws_iam_policy_document.async_task_execution_secrets.json
}

# Publisher can send only. It cannot consume or delete scan messages.
resource "aws_iam_role" "outbox_publisher" {
  name               = "${local.name_prefix}-outbox-publisher"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

data "aws_iam_policy_document" "outbox_publisher_sqs" {
  statement {
    sid       = "PublishScanMessages"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.scan.arn]
  }
}

resource "aws_iam_role_policy" "outbox_publisher_sqs" {
  name   = "publish-scan-messages"
  role   = aws_iam_role.outbox_publisher.id
  policy = data.aws_iam_policy_document.outbox_publisher_sqs.json
}

# Worker can consume/acknowledge only. It cannot publish new scan messages.
resource "aws_iam_role" "scan_worker" {
  name               = "${local.name_prefix}-scan-worker"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

data "aws_iam_policy_document" "scan_worker_sqs" {
  statement {
    sid    = "ConsumeScanMessages"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.scan.arn]
  }
}

resource "aws_iam_role_policy" "scan_worker_sqs" {
  name   = "consume-scan-messages"
  role   = aws_iam_role.scan_worker.id
  policy = data.aws_iam_policy_document.scan_worker_sqs.json
}

locals {
  async_database_environment = [
    { name = "AIRLOCK_DATABASE_HOST", value = aws_db_instance.airlock.address },
    { name = "AIRLOCK_DATABASE_PORT", value = tostring(aws_db_instance.airlock.port) },
    { name = "AIRLOCK_DATABASE_NAME", value = var.database_name },
    # Async roles process bounded batches/messages, so keep their per-task RDS budget below the API default.
    { name = "AIRLOCK_DATABASE_POOL_SIZE", value = "2" },
    { name = "AIRLOCK_DATABASE_MAX_OVERFLOW", value = "1" },
    { name = "AIRLOCK_DATABASE_POOL_TIMEOUT_SECONDS", value = "5" },
    { name = "AIRLOCK_DATABASE_POOL_RECYCLE_SECONDS", value = "900" },
    { name = "AIRLOCK_AUTO_CREATE_SCHEMA", value = "false" },
    { name = "AIRLOCK_RUN_MIGRATIONS", value = "false" },
  ]

  async_queue_environment = [
    { name = "AIRLOCK_SCAN_MODE", value = "queued" },
    { name = "AIRLOCK_SCAN_QUEUE_URL", value = aws_sqs_queue.scan.url },
    { name = "AIRLOCK_AWS_REGION", value = var.aws_region },
    { name = "AIRLOCK_OUTBOX_BATCH_SIZE", value = "10" },
    { name = "AIRLOCK_OUTBOX_CLAIM_TTL_SECONDS", value = "60" },
    { name = "AIRLOCK_SCAN_WORKER_CLAIM_TTL_SECONDS", value = tostring(var.scan_visibility_timeout_seconds) },
    { name = "AIRLOCK_SQS_WAIT_TIME_SECONDS", value = "20" },
    { name = "AIRLOCK_SQS_VISIBILITY_TIMEOUT_SECONDS", value = tostring(var.scan_visibility_timeout_seconds) },
  ]

  async_database_secrets = [
    {
      name      = "AIRLOCK_DATABASE_USER"
      valueFrom = "${aws_db_instance.airlock.master_user_secret[0].secret_arn}:username::"
    },
    {
      name      = "AIRLOCK_DATABASE_PASSWORD"
      valueFrom = "${aws_db_instance.airlock.master_user_secret[0].secret_arn}:password::"
    },
  ]
}

# -----------------------------------------------------------------------------
# Transactional-outbox publisher: PostgreSQL -> SQS.
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "outbox_publisher" {
  family                   = "${local.name_prefix}-outbox-publisher"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.async_task_execution.arn
  task_role_arn            = aws_iam_role.outbox_publisher.arn

  container_definitions = jsonencode([
    {
      name      = "outbox-publisher"
      image     = var.container_image
      essential = true
      command   = ["python", "-m", "app.workers.outbox_publisher"]
      environment = concat(
        local.async_database_environment,
        local.async_queue_environment,
      )
      secrets = local.async_database_secrets
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.airlock.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "outbox-publisher"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "outbox_publisher" {
  name            = "outbox-publisher"
  cluster         = aws_ecs_cluster.airlock.id
  task_definition = aws_ecs_task_definition.outbox_publisher.arn
  desired_count   = var.outbox_publisher_desired_count
  launch_type     = "FARGATE"

  enable_execute_command = false

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }
}

# -----------------------------------------------------------------------------
# Independent scan worker: SQS -> shared quarantine storage -> PostgreSQL result.
# -----------------------------------------------------------------------------

resource "aws_ecs_task_definition" "scan_worker" {
  family                   = "${local.name_prefix}-scan-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.async_task_execution.arn
  task_role_arn            = aws_iam_role.scan_worker.arn

  volume {
    name = "airlock-data"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.airlock.id
      transit_encryption = "ENABLED"
    }
  }

  container_definitions = jsonencode([
    {
      name      = "scan-worker"
      image     = var.container_image
      essential = true
      command   = ["python", "-m", "app.workers.scan_worker"]
      environment = concat(
        local.async_database_environment,
        local.async_queue_environment,
        [{ name = "AIRLOCK_QUARANTINE_DIR", value = "/mnt/airlock/quarantine" }],
      )
      secrets = local.async_database_secrets
      mountPoints = [
        {
          sourceVolume  = "airlock-data"
          containerPath = "/mnt/airlock"
          readOnly      = false
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.airlock.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "scan-worker"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "scan_worker" {
  name            = "scan-worker"
  cluster         = aws_ecs_cluster.airlock.id
  task_definition = aws_ecs_task_definition.scan_worker.arn
  desired_count   = var.scan_worker_desired_count
  launch_type     = "FARGATE"

  enable_execute_command = false

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  depends_on = [aws_efs_mount_target.airlock]
}
