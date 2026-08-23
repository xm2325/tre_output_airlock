provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      Service     = "airlock-api"
      DataClass   = "synthetic-demo"
      ManagedBy   = "terraform"
    }
  }
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# -----------------------------------------------------------------------------
# Network boundaries
# -----------------------------------------------------------------------------

resource "aws_security_group" "vpc_link" {
  name        = "${local.name_prefix}-apigw-vpc-link"
  description = "API Gateway VPC Link network interface"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_security_group" "load_balancer" {
  name        = "${local.name_prefix}-internal-alb"
  description = "Internal Airlock load balancer"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_security_group" "service" {
  name        = "${local.name_prefix}-service"
  description = "Airlock ECS tasks"
  vpc_id      = var.vpc_id

  # The service must reach RDS/EFS inside the VPC and the configured IdP over
  # HTTPS through the private subnets' NAT/egress path.
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "database" {
  name        = "${local.name_prefix}-rds"
  description = "PostgreSQL RDS reachable only from the Airlock service"
  vpc_id      = var.vpc_id
}

resource "aws_security_group" "efs" {
  name        = "${local.name_prefix}-efs"
  description = "Encrypted Airlock working-file storage"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "alb_from_vpc_link" {
  security_group_id            = aws_security_group.load_balancer.id
  referenced_security_group_id = aws_security_group.vpc_link.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "service_from_alb" {
  security_group_id            = aws_security_group.service.id
  referenced_security_group_id = aws_security_group.load_balancer.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "database_from_service" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.service.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_service" {
  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = aws_security_group.service.id
  from_port                    = 2049
  to_port                      = 2049
  ip_protocol                  = "tcp"
}

# -----------------------------------------------------------------------------
# PostgreSQL / RDS
# -----------------------------------------------------------------------------

resource "aws_db_subnet_group" "airlock" {
  name       = "${local.name_prefix}-db"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "airlock" {
  identifier = local.name_prefix

  engine         = "postgres"
  instance_class = var.database_instance_class
  db_name        = var.database_name
  username       = "airlockadmin"
  port           = 5432

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  manage_master_user_password = true
  publicly_accessible         = false
  multi_az                    = var.database_multi_az

  db_subnet_group_name   = aws_db_subnet_group.airlock.name
  vpc_security_group_ids = [aws_security_group.database.id]

  backup_retention_period   = var.environment == "prod" ? 14 : 7
  deletion_protection       = var.environment == "prod"
  skip_final_snapshot       = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${local.name_prefix}-final" : null

  auto_minor_version_upgrade = true
  apply_immediately          = var.environment != "prod"
}

# -----------------------------------------------------------------------------
# Durable encrypted working-file storage for the containerised service
# -----------------------------------------------------------------------------

resource "aws_efs_file_system" "airlock" {
  encrypted = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }
}

resource "aws_efs_mount_target" "airlock" {
  for_each = toset(var.private_subnet_ids)

  file_system_id  = aws_efs_file_system.airlock.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}

# -----------------------------------------------------------------------------
# ECS task identity, secrets and telemetry
# -----------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${local.name_prefix}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "task_execution_secrets" {
  statement {
    sid     = "ReadOnlyDeclaredRuntimeSecrets"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      aws_db_instance.airlock.master_user_secret[0].secret_arn,
      var.oidc_client_secret_arn,
      var.report_signing_secret_arn,
    ]
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  name   = "read-declared-airlock-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.task_execution_secrets.json
}

# The application currently calls no AWS control-plane APIs at runtime. Keep the
# task role intentionally empty rather than granting broad service permissions.
resource "aws_iam_role" "task" {
  name               = "${local.name_prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
}

resource "aws_cloudwatch_log_group" "airlock" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = 30
}

resource "aws_ecs_cluster" "airlock" {
  name = local.name_prefix
}

resource "aws_ecs_task_definition" "airlock" {
  family                   = local.name_prefix
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"
  memory                   = "1024"
  execution_role_arn       = aws_iam_role.task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  volume {
    name = "airlock-data"

    efs_volume_configuration {
      file_system_id     = aws_efs_file_system.airlock.id
      transit_encryption = "ENABLED"
    }
  }

  container_definitions = jsonencode([
    {
      name      = "airlock-api"
      image     = var.container_image
      essential = true

      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
          protocol      = "tcp"
        }
      ]

      environment = [
        { name = "AIRLOCK_AUTH_MODE", value = "oidc_introspection" },
        { name = "AIRLOCK_OIDC_INTROSPECTION_URL", value = var.oidc_introspection_url },
        { name = "AIRLOCK_OIDC_CLIENT_ID", value = var.oidc_client_id },
        { name = "AIRLOCK_OIDC_EXPECTED_AUDIENCE", value = var.oidc_expected_audience },
        { name = "AIRLOCK_OIDC_EXPECTED_ISSUER", value = var.oidc_expected_issuer },
        { name = "AIRLOCK_OIDC_ROLE_CLAIM", value = "groups" },
        { name = "AIRLOCK_OIDC_CACHE_TTL_SECONDS", value = tostring(var.oidc_cache_ttl_seconds) },
        { name = "AIRLOCK_OIDC_CACHE_MAX_ENTRIES", value = tostring(var.oidc_cache_max_entries) },
        { name = "AIRLOCK_DATABASE_HOST", value = aws_db_instance.airlock.address },
        { name = "AIRLOCK_DATABASE_PORT", value = tostring(aws_db_instance.airlock.port) },
        { name = "AIRLOCK_DATABASE_NAME", value = var.database_name },
        { name = "AIRLOCK_AUTO_CREATE_SCHEMA", value = "false" },
        { name = "AIRLOCK_RUN_MIGRATIONS", value = "false" },
        { name = "AIRLOCK_QUARANTINE_DIR", value = "/mnt/airlock/quarantine" },
        { name = "AIRLOCK_CORS_ORIGINS", value = var.cors_origins },
      ]

      secrets = [
        {
          name      = "AIRLOCK_DATABASE_USER"
          valueFrom = "${aws_db_instance.airlock.master_user_secret[0].secret_arn}:username::"
        },
        {
          name      = "AIRLOCK_DATABASE_PASSWORD"
          valueFrom = "${aws_db_instance.airlock.master_user_secret[0].secret_arn}:password::"
        },
        {
          name      = "AIRLOCK_OIDC_CLIENT_SECRET"
          valueFrom = var.oidc_client_secret_arn
        },
        {
          name      = "AIRLOCK_REPORT_SIGNING_SECRET"
          valueFrom = var.report_signing_secret_arn
        },
      ]

      mountPoints = [
        {
          sourceVolume  = "airlock-data"
          containerPath = "/mnt/airlock"
          readOnly      = false
        }
      ]

      healthCheck = {
        command = [
          "CMD-SHELL",
          "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)\" || exit 1",
        ]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 30
      }

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.airlock.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}

# -----------------------------------------------------------------------------
# Internal load balancer + API Gateway HTTP API
# -----------------------------------------------------------------------------

resource "aws_lb" "airlock" {
  name               = substr(replace(local.name_prefix, "_", "-"), 0, 32)
  internal           = true
  load_balancer_type = "application"
  security_groups    = [aws_security_group.load_balancer.id]
  subnets            = var.private_subnet_ids
}

resource "aws_lb_target_group" "airlock" {
  name        = substr("${replace(local.name_prefix, "_", "-")}-api", 0, 32)
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    enabled             = true
    path                = "/ready"
    port                = "traffic-port"
    protocol            = "HTTP"
    matcher             = "200"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }
}

resource "aws_lb_listener" "airlock" {
  load_balancer_arn = aws_lb.airlock.arn
  port              = 8000
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.airlock.arn
  }
}

resource "aws_ecs_service" "airlock" {
  name            = "airlock-api"
  cluster         = aws_ecs_cluster.airlock.id
  task_definition = aws_ecs_task_definition.airlock.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  enable_execute_command = false

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.airlock.arn
    container_name   = "airlock-api"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.airlock,
    aws_efs_mount_target.airlock,
  ]
}

resource "aws_apigatewayv2_api" "airlock" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_vpc_link" "airlock" {
  name               = "${local.name_prefix}-vpc-link"
  security_group_ids = [aws_security_group.vpc_link.id]
  subnet_ids         = var.private_subnet_ids
}

resource "aws_apigatewayv2_integration" "airlock" {
  api_id                 = aws_apigatewayv2_api.airlock.id
  integration_type       = "HTTP_PROXY"
  integration_method     = "ANY"
  integration_uri        = aws_lb_listener.airlock.arn
  connection_type        = "VPC_LINK"
  connection_id          = aws_apigatewayv2_vpc_link.airlock.id
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id    = aws_apigatewayv2_api.airlock.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.airlock.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.airlock.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }
}
