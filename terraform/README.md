# ascii-player AWS Deployment Terraform

AWS infrastructure for running ascii-player on EC2.

## Prerequisites
- AWS CLI configured with credentials
- Terraform 1.0+
- EC2 key pair for SSH access
- Your current public IP address

## Quick Start

1. Get your current IP:
```bash
export MY_IP=$(curl -s https://checkip.amazonaws.com)
```

2. Initialize:
```bash
terraform init
```

3. Review:
```bash
terraform plan -var="allowed_ssh_cidr=$MY_IP" -var="key_pair_name=YOUR_KEY_PAIR"
```

4. Deploy:
```bash
terraform apply -var="allowed_ssh_cidr=$MY_IP" -var="key_pair_name=YOUR_KEY_PAIR"
```

5. SSH in:
```bash
ssh -i your-key.pem ubuntu@$(terraform output -raw ssh_command | sed 's/.*ubuntu@//')
```

## Running the Application

After SSH-ing into the instance:

```bash
# Pull and run your pre-built image
docker pull ascii-player:latest
docker run -it --rm --device=/dev/snd --device=/dev/dri ascii-player:latest --webcam --width=80

# Or play a local video
docker run -it --rm -v $(pwd):/data ascii-player:latest /data/sample.mp4
```

## Cost Estimate
~$9-12/month for t3.micro instance + Elastic IP + S3 storage

## Cleanup
```bash
terraform destroy -var="allowed_ssh_cidr=$MY_IP" -var="key_pair_name=YOUR_KEY_PAIR"
```

## Files
- `main.tf` - Main infrastructure (VPC, EC2, S3, IAM)
- `variables.tf` - Input variables
- `user_data.sh` - Boot script for EC2 instance