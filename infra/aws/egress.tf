# #33: workers may reach the model provider and nothing else outside AWS.
# Security groups can't filter by name, so a stateful firewall allows only TLS to the listed domains (by SNI).

locals {
  # The model provider, and Clerk, whose signing keys the API fetches to check sign-in tokens.
  egress_domains = concat(var.llm_egress_domains, [trimprefix(trimsuffix(var.clerk_issuer, "/"), "https://")])
}

resource "aws_networkfirewall_rule_group" "llm_only" {
  count    = var.enable_network_firewall ? 1 : 0
  name     = "${local.name}-llm-only"
  type     = "STATEFUL"
  capacity = 100

  rule_group {
    rules_source {
      rules_source_list {
        generated_rules_type = "ALLOWLIST"
        target_types         = ["TLS_SNI"]
        targets              = local.egress_domains
      }
    }
  }
}

resource "aws_networkfirewall_firewall_policy" "main" {
  count = var.enable_network_firewall ? 1 : 0
  name  = "${local.name}-egress"

  firewall_policy {
    stateless_default_actions          = ["aws:forward_to_sfe"]
    stateless_fragment_default_actions = ["aws:forward_to_sfe"]
    stateful_default_actions           = ["aws:drop_established", "aws:alert_established"]
    stateful_engine_options {
      rule_order = "STRICT_ORDER"
    }
    stateful_rule_group_reference {
      priority     = 1
      resource_arn = aws_networkfirewall_rule_group.llm_only[0].arn
    }
  }
}

resource "aws_networkfirewall_firewall" "main" {
  count               = var.enable_network_firewall ? 1 : 0
  name                = "${local.name}-egress"
  vpc_id              = aws_vpc.main.id
  firewall_policy_arn = aws_networkfirewall_firewall_policy.main[0].arn

  dynamic "subnet_mapping" {
    for_each = aws_subnet.firewall
    content {
      subnet_id = subnet_mapping.value.id
    }
  }
}

locals {
  firewall_endpoints = var.enable_network_firewall ? {
    for state in aws_networkfirewall_firewall.main[0].firewall_status[0].sync_states :
    state.availability_zone => state.attachment[0].endpoint_id
  } : {}
}

# Traffic the firewall allowed goes on through NAT in the same zone.
resource "aws_route_table" "firewall" {
  for_each = var.enable_network_firewall ? local.index : {}
  vpc_id   = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main[each.key].id
  }
}

resource "aws_route_table_association" "firewall" {
  for_each       = aws_subnet.firewall
  subnet_id      = each.value.id
  route_table_id = aws_route_table.firewall[each.key].id
}

# Replies from NAT to the app subnets return through the firewall, so it sees both directions.
resource "aws_route" "nat_return" {
  for_each               = var.enable_network_firewall ? local.index : {}
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = aws_subnet.app[each.key].cidr_block
  vpc_endpoint_id        = local.firewall_endpoints[each.key]
}

resource "aws_cloudwatch_log_group" "firewall" {
  count             = var.enable_network_firewall ? 1 : 0
  name              = "/meridian/${var.environment}/egress-firewall"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
}

resource "aws_networkfirewall_logging_configuration" "main" {
  count        = var.enable_network_firewall ? 1 : 0
  firewall_arn = aws_networkfirewall_firewall.main[0].arn
  logging_configuration {
    log_destination_config {
      log_type             = "ALERT"
      log_destination_type = "CloudWatchLogs"
      log_destination      = { logGroup = aws_cloudwatch_log_group.firewall[0].name }
    }
  }
}
