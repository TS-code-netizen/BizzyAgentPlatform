resource "aws_cloudwatch_log_metric_filter" "fallback" {
  name           = "bedrock-fallback"
  log_group_name = aws_cloudwatch_log_group.lambda.name
  pattern        = "\"bedrock_routing\" \"true\""
  metric_transformation {
    name      = "InferenceFallback"
    namespace = "BizzyBee/POC"
    value     = "1"
  }
}
resource "aws_cloudwatch_metric_alarm" "fallback" {
  alarm_name          = "${local.name}-inference-fallback"
  namespace           = "BizzyBee/POC"
  metric_name         = "InferenceFallback"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 3
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}
