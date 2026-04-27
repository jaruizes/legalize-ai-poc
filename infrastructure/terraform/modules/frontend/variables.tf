variable "name_prefix" {
  description = "Name prefix applied to all resources"
  type        = string
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for the frontend app"
  type        = string
}

variable "api_domain" {
  description = "Lambda Function URL domain without scheme (e.g. abc.lambda-url.eu-west-1.on.aws)"
  type        = string
}

variable "ui_title" {
  type        = string
  description = "Application title"
}

variable "ui_subtitle" {
  type        = string
  description = "Application subtitle"
}

variable "ui_icon" {
  type        = string
  description = "Application icon"
}

variable "ui_examples" {
  type        = list(string)
  description = "List of example questions"
}

variable "ui_disclaimer" {
  type        = string
  description = "Disclaimer text for the footer"
}
