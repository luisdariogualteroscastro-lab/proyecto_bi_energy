# ===========================================================================
# Infraestructura como Código (Terraform) - Bia Energy Data Platform
# ===========================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# 1. Llave KMS para Cifrado en Reposo
resource "aws_kms_key" "bia_kms" {
  description             = "Llave maestra KMS para cifrado en reposo de PII y datos sensibles - Bia Energy"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Environment = "Production"
    Project     = "Bia-Data-Platform"
    Compliance  = "ISO-27001-Ley-1581"
  }
}

resource "aws_kms_alias" "bia_kms_alias" {
  name          = "alias/bia-data-platform-key"
  target_key_id = aws_kms_key.bia_kms.key_id
}

# 2. Bucket S3 para Ingesta Cruda (con cifrado y versionado)
resource "aws_s3_bucket" "bia_raw_bucket" {
  bucket = "bia-data-platform-raw-prod"

  tags = {
    Environment = "Production"
    DataClass   = "Restringido-PII"
  }
}

resource "aws_s3_bucket_versioning" "raw_versioning" {
  bucket = aws_s3_bucket.bia_raw_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw_encryption" {
  bucket = aws_s3_bucket.bia_raw_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.bia_kms.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "raw_public_block" {
  bucket                  = aws_s3_bucket.bia_raw_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 3. Roles IAM (Principio de Menor Privilegio equivalente a C4 de Postgres)

# Rol IAM: Ingesta (escribe en S3 y base analítica, sin acceso a PII en claro)
resource "aws_iam_role" "rol_ingesta" {
  name = "bia-ingesta-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "policy_ingesta" {
  name = "bia-ingesta-policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.bia_raw_bucket.arn,
          "${aws_s3_bucket.bia_raw_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.bia_kms.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "attach_ingesta" {
  role       = aws_iam_role.rol_ingesta.name
  policy_arn = aws_iam_policy.policy_ingesta.arn
}

# Rol IAM: Analista (solo lectura de vistas analíticas / reportes, sin PII ni S3 raw)
resource "aws_iam_role" "rol_analista" {
  name = "bia-analista-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "quicksight.amazonaws.com"
        }
      }
    ]
  })
}

# Rol IAM: Auditor (acceso de lectura a logs y bitácoras de auditoría, sin PII)
resource "aws_iam_role" "rol_auditor" {
  name = "bia-auditor-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "cloudwatch.amazonaws.com"
        }
      }
    ]
  })
}
