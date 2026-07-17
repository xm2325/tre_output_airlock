output "bucket_names" {
  description = "Data-zone bucket names."
  value       = { for name, bucket in aws_s3_bucket.data : name => bucket.bucket }
}

output "delivery_queue_url" {
  description = "Queue used to trigger delivery processing."
  value       = aws_sqs_queue.delivery.url
}

output "pipeline_policy_arn" {
  description = "Least-privilege policy to attach to the pipeline runtime role."
  value       = aws_iam_policy.pipeline.arn
}
