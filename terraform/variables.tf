variable "aws_region" {
  description = "AWS region to deploy to"
  type        = string
  default     = "ap-southeast-1"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "key_pair_name" {
  description = "Name of existing EC2 key pair"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "Your IP address for SSH access"
  type        = string
}