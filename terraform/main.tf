terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# --- VPC + Networking ---
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "ascii-player-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags = { Name = "ascii-player-igw" }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
  tags = { Name = "ascii-player-public" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "ascii-player-public-rt" }
}

resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# --- Security ---
resource "aws_security_group" "bot_sg" {
  name        = "ascii-player-sg"
  description = "Security group for ascii-player bot"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${var.allowed_ssh_cidr}/32"]
  }

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "ascii-player-sg" }
}

# --- S3 Bucket ---
resource "aws_s3_bucket" "media_cache" {
  bucket = "ascii-player-cache-${random_string.suffix.result}"
  tags   = { Name = "ascii-player-cache" }
}

resource "aws_s3_bucket_public_access_block" "media_cache" {
  bucket                  = aws_s3_bucket.media_cache.id
  block_public_acls       = true
  block_public_policy     = true
  restrict_public_buckets = true
  ignore_public_acls      = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "media_cache" {
  bucket = aws_s3_bucket.media_cache.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }

# --- IAM Roles ---
resource "aws_iam_role" "ec2_role" {
  name = "ascii-player-ec2-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "ec2_policy" {
  name = "ascii-player-ec2-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.media_cache.arn}/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:ListBucket"]
        Resource = aws_s3_bucket.media_cache.arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ec2_attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.ec2_policy.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "ascii-player-instance-profile"
  role = aws_iam_role.ec2_role.name
}

# --- EC2 Instance ---
resource "aws_instance" "bot_server" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.bot_sg.id]
  key_name                    = var.key_pair_name != "" ? var.key_pair_name : null
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name
  associate_public_ip_address = true
  user_data                   = base64encode(templatefile("${path.module}/user_data.sh", {
    aws_region = var.aws_region
  }))
  tags = {
    Name        = "ascii-player-bot"
    Environment = "prod"
  }
  lifecycle {
    ignore_changes = [user_data]
  }
}

data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099724104104"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# --- Elastic IP ---
resource "aws_eip" "bot_eip" {
  domain = "vpc"
  tags   = { Name = "ascii-player-eip" }
}

resource "aws_eip_association" "bot_eip_assoc" {
  allocation_id = aws_eip.bot_eip.id
  instance_id   = aws_instance.bot_server.id
}

# --- CloudWatch Log Group ---
resource "aws_cloudwatch_log_group" "bot_logs" {
  name              = "/aws/ec2/ascii-player"
  retention_in_days = 30
}

# --- Random suffix for S3 bucket ---
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# --- Outputs ---
output "bot_url" {
  value = "http://${aws_eip.bot_eip.public_ip}"
  description = "SSH URL to access ascii-player server"
}

output "ssh_command" {
  value = "ssh -i YOUR_KEY.pem ubuntu@${aws_eip.bot_eip.public_ip}"
}

output "s3_bucket_name" {
  value = aws_s3_bucket.media_cache.bucket
}