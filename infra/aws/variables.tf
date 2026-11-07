variable "environment" {
  description = "staging or production. Each has its own state, network and data."
  type        = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Use staging or production."
  }
}

variable "region" {
  description = "AWS region for everything except CloudFront's certificate and WAF."
  type        = string
  default     = "ap-south-1"
}

variable "domain_name" {
  description = "Public name for the website and API, e.g. app.example.com. Its hosted zone must exist in Route 53."
  type        = string
}

variable "hosted_zone_id" {
  description = "Route 53 hosted zone that holds domain_name."
  type        = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.40.0.0/16"
}

variable "image_tag" {
  description = "Image tag to run, normally the git commit. The pipeline sets it."
  type        = string
  default     = "latest"
}

variable "llm_egress_domains" {
  description = "The only hosts workers may reach outside AWS: the model provider."
  type        = list(string)
  default     = ["generativelanguage.googleapis.com"]
}

variable "enable_network_firewall" {
  description = "Domain allow-list for worker traffic (#33). About USD 290 a month per zone, so staging may turn it off and rely on security groups."
  type        = bool
  default     = true
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}

variable "db_multi_az" {
  type    = bool
  default = false
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}

variable "api_count" {
  type    = number
  default = 1
}

variable "worker_count" {
  type    = number
  default = 1
}

variable "web_count" {
  type    = number
  default = 1
}

variable "alert_email" {
  description = "Where alarms are sent. The address must confirm the SNS subscription."
  type        = string
}

variable "llm_model" {
  type    = string
  default = "gemini-3.1-flash-lite"
}

variable "llm_base_url" {
  type    = string
  default = "https://generativelanguage.googleapis.com/v1beta/openai"
}

variable "clerk_issuer" {
  description = "Clerk instance URL, e.g. https://example.clerk.accounts.dev"
  type        = string
}
