variable "aws_region" {
  description = "AWS region for the reference deployment."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Short service name used in AWS resource names and tags."
  type        = string
  default     = "tre-output-airlock"
}

variable "environment" {
  description = "Deployment environment such as dev, staging or prod."
  type        = string

  default = "dev"
}

variable "vpc_id" {
  description = "Existing VPC in which the private service will run."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR of the existing VPC, used for constrained internal egress."
  type        = string
}

variable "private_subnet_ids" {
  description = "At least two private subnets across availability zones."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "Provide at least two private subnet IDs."
  }
}

variable "container_image" {
  description = "Immutable Airlock API image reference, ideally pinned by digest."
  type        = string
}

variable "desired_count" {
  description = "Number of ECS service tasks."
  type        = number
  default     = 2
}

variable "database_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "airlock"
}

variable "database_instance_class" {
  description = "RDS instance class for the reference deployment."
  type        = string
  default     = "db.t4g.micro"
}

variable "database_multi_az" {
  description = "Whether the RDS instance is Multi-AZ."
  type        = bool
  default     = false
}

variable "database_pool_size" {
  description = "Persistent PostgreSQL connections retained by each API task."
  type        = number
  default     = 5

  validation {
    condition     = var.database_pool_size >= 1 && var.database_pool_size <= 20
    error_message = "Database pool size must be between 1 and 20 connections per task."
  }
}

variable "database_max_overflow" {
  description = "Temporary PostgreSQL connections allowed above pool_size for each API task."
  type        = number
  default     = 5

  validation {
    condition     = var.database_max_overflow >= 0 && var.database_max_overflow <= 20
    error_message = "Database max overflow must be between 0 and 20 connections per task."
  }
}

variable "database_pool_timeout_seconds" {
  description = "Maximum time an API request waits for a PostgreSQL connection checkout."
  type        = number
  default     = 5

  validation {
    condition = (
      var.database_pool_timeout_seconds >= 0.1 &&
      var.database_pool_timeout_seconds <= 30
    )
    error_message = "Database pool timeout must be between 0.1 and 30 seconds."
  }
}

variable "database_pool_recycle_seconds" {
  description = "Maximum age before a checked-out PostgreSQL connection is recycled."
  type        = number
  default     = 900

  validation {
    condition = (
      var.database_pool_recycle_seconds >= 30 &&
      var.database_pool_recycle_seconds <= 3600
    )
    error_message = "Database pool recycle interval must be between 30 and 3600 seconds."
  }
}

variable "oidc_introspection_url" {
  description = "OIDC/OAuth2 token introspection endpoint, for example an Okta authorization server."
  type        = string
}

variable "oidc_client_id" {
  description = "OAuth2 client ID used by the Airlock API for token introspection."
  type        = string
}

variable "oidc_client_secret_arn" {
  description = "Secrets Manager ARN containing only the OAuth2 introspection client secret."
  type        = string
  sensitive   = true
}

variable "oidc_expected_audience" {
  description = "Expected access-token audience."
  type        = string
}

variable "oidc_expected_issuer" {
  description = "Expected authorization-server issuer."
  type        = string
}

variable "oidc_cache_ttl_seconds" {
  description = "Short successful-introspection cache TTL. Zero disables caching; values above 60 are rejected by the application."
  type        = number
  default     = 15

  validation {
    condition     = var.oidc_cache_ttl_seconds >= 0 && var.oidc_cache_ttl_seconds <= 60
    error_message = "OIDC cache TTL must be between 0 and 60 seconds."
  }
}

variable "oidc_cache_max_entries" {
  description = "Per-task maximum number of successful token introspection entries retained in the LRU cache."
  type        = number
  default     = 2048

  validation {
    condition     = var.oidc_cache_max_entries >= 1 && var.oidc_cache_max_entries <= 10000
    error_message = "OIDC cache capacity must be between 1 and 10000 entries."
  }
}

variable "report_signing_secret_arn" {
  description = "Secrets Manager ARN containing the HMAC decision-report signing secret."
  type        = string
  sensitive   = true
}

variable "cors_origins" {
  description = "Comma-separated trusted frontend origins."
  type        = string
  default     = ""
}
