variable "aws_region" {
  description = "AWS region for the demonstration resources."
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Short resource-name prefix."
  type        = string
  default     = "tre-clinical-genomic"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "demo"
}

variable "force_destroy" {
  description = "Allow bucket deletion with objects. Keep false outside disposable demos."
  type        = bool
  default     = false
}
