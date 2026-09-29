variable "enable_github_deployment" {
  type        = bool
  default     = false
  description = "Enable only after verifying and approving protected GitHub deployment environments."
}
data "aws_iam_openid_connect_provider" "github" {
  count = var.enable_github_deployment ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}
resource "aws_iam_role" "deploy" {
  for_each = var.enable_github_deployment ? { backend = "BizzyBackend", frontend = "BizzyFrontend" } : {}
  name     = "${local.name}-${each.key}-deploy"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Federated = data.aws_iam_openid_connect_provider.github[0].arn },
    Action = "sts:AssumeRoleWithWebIdentity",
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = "repo:BizzyBeeAI/${each.value}:environment:poc"
    } }
  }] })
}
resource "aws_iam_role_policy" "backend_deploy" {
  count = var.enable_github_deployment ? 1 : 0
  role  = aws_iam_role.deploy["backend"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
    { Effect = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"], Resource = local.repo_arn },
    { Effect = "Allow", Action = ["lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:UpdateFunctionCode", "lambda:PublishVersion"], Resource = aws_lambda_function.backend.arn },
    { Effect = "Allow", Action = ["lambda:GetAlias", "lambda:UpdateAlias"], Resource = aws_lambda_alias.live.arn },
    { Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = "${aws_lambda_function.backend.arn}:*" }
  ] })
}
resource "aws_iam_role_policy" "frontend_deploy" {
  count = var.enable_github_deployment ? 1 : 0
  role  = aws_iam_role.deploy["frontend"].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect   = "Allow", Action = ["amplify:CreateDeployment", "amplify:StartDeployment", "amplify:GetJob"],
    Resource = ["${aws_amplify_app.frontend.arn}/branches/poc", "${aws_amplify_app.frontend.arn}/branches/poc/jobs/*"]
  }] })
}
output "backend_deploy_role_arn" { value = try(aws_iam_role.deploy["backend"].arn, null) }
output "frontend_deploy_role_arn" { value = try(aws_iam_role.deploy["frontend"].arn, null) }
output "runtime_role_arn" { value = aws_iam_role.runtime.arn }
