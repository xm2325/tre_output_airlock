variable "async_alarm_actions" {
  description = "Optional SNS topic ARNs or other CloudWatch alarm action ARNs for async pipeline alerts."
  type        = list(string)
  default     = []
}

variable "scan_queue_backlog_alarm_threshold" {
  description = "Visible scan messages that trigger a sustained backlog alarm."
  type        = number
  default     = 50

  validation {
    condition     = var.scan_queue_backlog_alarm_threshold >= 1
    error_message = "Scan queue backlog alarm threshold must be at least 1."
  }
}

variable "scan_queue_oldest_age_alarm_seconds" {
  description = "Age in seconds of the oldest scan message that triggers an alarm."
  type        = number
  default     = 300

  validation {
    condition     = var.scan_queue_oldest_age_alarm_seconds >= 60
    error_message = "Scan queue oldest-age alarm threshold must be at least 60 seconds."
  }
}

variable "scan_dlq_alarm_threshold" {
  description = "Visible DLQ messages that trigger an immediate alarm."
  type        = number
  default     = 1

  validation {
    condition     = var.scan_dlq_alarm_threshold >= 1
    error_message = "Scan DLQ alarm threshold must be at least 1."
  }
}

resource "aws_cloudwatch_metric_alarm" "scan_queue_backlog" {
  alarm_name          = "${local.name_prefix}-scan-queue-backlog"
  alarm_description   = "Scan queue visible backlog is above the configured operating threshold."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.scan_queue_backlog_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.async_alarm_actions
  ok_actions          = var.async_alarm_actions

  dimensions = {
    QueueName = aws_sqs_queue.scan.name
  }
}

resource "aws_cloudwatch_metric_alarm" "scan_queue_oldest_age" {
  alarm_name          = "${local.name_prefix}-scan-queue-oldest-age"
  alarm_description   = "The oldest visible scan message has waited too long for processing."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  datapoints_to_alarm = 2
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.scan_queue_oldest_age_alarm_seconds
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.async_alarm_actions
  ok_actions          = var.async_alarm_actions

  dimensions = {
    QueueName = aws_sqs_queue.scan.name
  }
}

resource "aws_cloudwatch_metric_alarm" "scan_dlq_depth" {
  alarm_name          = "${local.name_prefix}-scan-dlq-depth"
  alarm_description   = "At least one scan message has reached the dead-letter queue."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.scan_dlq_alarm_threshold
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.async_alarm_actions
  ok_actions          = var.async_alarm_actions

  dimensions = {
    QueueName = aws_sqs_queue.scan_dlq.name
  }
}
