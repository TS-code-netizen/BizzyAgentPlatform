terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "6.14.1" }
  }
  backend "s3" {}
}
provider "aws" {
  region              = "ap-southeast-1"
  allowed_account_ids = ["524097108092"]
  default_tags { tags = { Project = "BizzyBee", Environment = "poc" } }
}
variable "image_digest" {
  type = string
  validation {
    condition     = can(regex("^sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Use the tested ECR image digest, never a moving tag."
  }
}
variable "model_id" {
  type    = string
  default = ""
}
variable "model_arns" {
  type    = list(string)
  default = []
  validation {
    condition     = alltrue([for arn in var.model_arns : startswith(arn, "arn:aws:bedrock:") && !strcontains(arn, "*")])
    error_message = "Only exact reviewed profile and destination model ARNs are allowed."
  }
}
variable "enable_inference" {
  type    = bool
  default = false
}
locals {
  name      = "bizzybee-poc"
  account   = "524097108092"
  region    = "ap-southeast-1"
  origin    = "https://poc.${aws_amplify_app.frontend.default_domain}"
  repo_name = "bizzybee-poc-backend"
  repo_arn  = "arn:aws:ecr:${local.region}:${local.account}:repository/${local.repo_name}"
}

resource "aws_amplify_app" "frontend" {
  name     = "${local.name}-frontend"
  platform = "WEB"
  custom_rule {
    source = "</^[^.]+$|\\.(?!(css|gif|ico|jpg|jpeg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>"
    target = "/index.html"
    status = "200"
  }
  custom_headers = trimspace(<<-HEADERS
    [{"pattern":"**","headers":[{"key":"Referrer-Policy","value":"no-referrer"},{"key":"X-Content-Type-Options","value":"nosniff"},{"key":"X-Frame-Options","value":"DENY"}]}]
  HEADERS
  )
}
resource "aws_amplify_branch" "poc" {
  app_id            = aws_amplify_app.frontend.id
  branch_name       = "poc"
  enable_auto_build = false
  stage             = "DEVELOPMENT"
}
resource "aws_cognito_user_pool" "users" {
  name                     = local.name
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  deletion_protection      = "ACTIVE"
  admin_create_user_config { allow_admin_create_user_only = true }
  password_policy {
    minimum_length                   = 12
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}
resource "aws_cognito_user_pool_domain" "login" {
  domain       = "${local.name}-${local.account}"
  user_pool_id = aws_cognito_user_pool.users.id
}
resource "aws_cognito_user_pool_client" "web" {
  name                                 = "${local.name}-web"
  user_pool_id                         = aws_cognito_user_pool.users.id
  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email"]
  supported_identity_providers         = ["COGNITO"]
  callback_urls                        = ["${local.origin}/"]
  logout_urls                          = ["${local.origin}/"]
  prevent_user_existence_errors        = "ENABLED"
  enable_token_revocation              = true
  access_token_validity                = 15
  id_token_validity                    = 15
  refresh_token_validity               = 1
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
resource "aws_cognito_user_group" "approvers" {
  name         = "approvers"
  user_pool_id = aws_cognito_user_pool.users.id
}
resource "aws_dynamodb_table" "audit" {
  name                        = "${local.name}-audit"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "workflow_id"
  deletion_protection_enabled = true
  attribute {
    name = "workflow_id"
    type = "S"
  }
  server_side_encryption { enabled = true }
  point_in_time_recovery { enabled = true }
  lifecycle { prevent_destroy = true }
}
resource "aws_iam_role" "runtime" {
  name = "${local.name}-runtime"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.name}-backend"
  retention_in_days = 14
}
resource "aws_iam_role_policy" "runtime" {
  role = aws_iam_role.runtime.id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat([
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.lambda.arn}:*" },
    { Effect = "Allow", Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"], Resource = aws_dynamodb_table.audit.arn }
  ], var.enable_inference ? [{ Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = var.model_arns }] : []) })
}
resource "aws_ecr_repository_policy" "lambda" {
  repository = local.repo_name
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Principal = { Service = "lambda.amazonaws.com" },
    Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
    Condition = { ArnLike = { "aws:SourceArn" = "arn:aws:lambda:${local.region}:${local.account}:function:${local.name}-backend" } }
  }] })
}
resource "aws_lambda_function" "backend" {
  function_name                  = "${local.name}-backend"
  role                           = aws_iam_role.runtime.arn
  package_type                   = "Image"
  image_uri                      = "${local.account}.dkr.ecr.${local.region}.amazonaws.com/${local.repo_name}@${var.image_digest}"
  architectures                  = ["x86_64"]
  timeout                        = 29
  memory_size                    = 1024
  reserved_concurrent_executions = 2
  publish                        = true
  environment {
    variables = {
      APP_ENV                = "poc"
      COGNITO_ISSUER         = "https://cognito-idp.${local.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
      COGNITO_CLIENT_ID      = aws_cognito_user_pool_client.web.id
      CORS_ORIGINS           = local.origin
      BIZZY_AUDIT_TABLE      = aws_dynamodb_table.audit.name
      BIZZY_RECORD_QUESTIONS = "false"
      BIZZY_MODEL_PROVIDER   = var.enable_inference ? "bedrock" : "disabled"
      BEDROCK_MODEL_ID       = var.model_id
      BEDROCK_MAX_TOKENS     = "128"
      BEDROCK_READ_TIMEOUT   = "6"
    }
  }
  lifecycle {
    ignore_changes = [image_uri]
    precondition {
      condition     = !var.enable_inference || (var.model_id != "" && length(var.model_arns) > 0)
      error_message = "Inference requires explicit reviewed model ID and target ARNs."
    }
  }
  depends_on = [aws_iam_role_policy.runtime, aws_ecr_repository_policy.lambda]
}
resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.backend.function_name
  function_version = aws_lambda_function.backend.version
  lifecycle { ignore_changes = [function_version] }
}
resource "aws_apigatewayv2_api" "api" {
  name          = local.name
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = [local.origin]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["authorization", "content-type"]
    max_age       = 300
  }
}
resource "aws_apigatewayv2_integration" "backend" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_alias.live.invoke_arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}
resource "aws_apigatewayv2_authorizer" "cognito" {
  api_id           = aws_apigatewayv2_api.api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito"
  jwt_configuration {
    audience = [aws_cognito_user_pool_client.web.id]
    issuer   = "https://cognito-idp.${local.region}.amazonaws.com/${aws_cognito_user_pool.users.id}"
  }
}
resource "aws_apigatewayv2_route" "api" {
  api_id               = aws_apigatewayv2_api.api.id
  route_key            = "ANY /api/v1/{proxy+}"
  target               = "integrations/${aws_apigatewayv2_integration.backend.id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.cognito.id
  authorization_scopes = ["openid"]
}
resource "aws_apigatewayv2_route" "health" {
  for_each  = toset(["health", "ready"])
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /${each.key}"
  target    = "integrations/${aws_apigatewayv2_integration.backend.id}"
}
resource "aws_apigatewayv2_route" "preflight" {
  api_id             = aws_apigatewayv2_api.api.id
  route_key          = "OPTIONS /api/v1/{proxy+}"
  target             = "integrations/${aws_apigatewayv2_integration.backend.id}"
  authorization_type = "NONE"
}
resource "aws_cloudwatch_log_group" "api" {
  name              = "/bizzybee/poc/api"
  retention_in_days = 14
}
resource "aws_apigatewayv2_stage" "poc" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 5
    throttling_rate_limit  = 2
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api.arn
    format          = jsonencode({ requestId = "$context.requestId", route = "$context.routeKey", status = "$context.status", latency = "$context.responseLatency" })
  }
}
resource "aws_lambda_permission" "api" {
  statement_id  = "ApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  qualifier     = aws_lambda_alias.live.name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${local.name}-backend-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.backend.function_name }
}
resource "aws_cloudwatch_metric_alarm" "duration" {
  alarm_name          = "${local.name}-backend-duration"
  namespace           = "AWS/Lambda"
  metric_name         = "Duration"
  extended_statistic  = "p95"
  period              = 300
  evaluation_periods  = 2
  threshold           = 25000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { FunctionName = aws_lambda_function.backend.function_name }
}
output "frontend_url" { value = local.origin }
output "api_url" { value = aws_apigatewayv2_api.api.api_endpoint }
output "cognito_issuer" { value = "https://cognito-idp.${local.region}.amazonaws.com/${aws_cognito_user_pool.users.id}" }
output "cognito_client_id" { value = aws_cognito_user_pool_client.web.id }
output "cognito_domain" { value = "https://${aws_cognito_user_pool_domain.login.domain}.auth.${local.region}.amazoncognito.com" }
output "user_pool_id" { value = aws_cognito_user_pool.users.id }
output "amplify_app_id" { value = aws_amplify_app.frontend.id }
