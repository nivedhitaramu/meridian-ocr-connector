data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name  = "meridian-${var.environment}"
  azs   = slice(data.aws_availability_zones.available.names, 0, 2)
  index = { for i, az in local.azs : az => i }
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

# Public: load balancer and NAT only.
resource "aws_subnet" "public" {
  for_each                = local.index
  vpc_id                  = aws_vpc.main.id
  availability_zone       = each.key
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, each.value)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-public-${each.key}" }
}

# App: API, web and workers. No public addresses.
resource "aws_subnet" "app" {
  for_each          = local.index
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 10 + each.value)
  tags              = { Name = "${local.name}-app-${each.key}" }
}

# Data: PostgreSQL and Redis. No route to the internet at all.
resource "aws_subnet" "data" {
  for_each          = local.index
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 20 + each.value)
  tags              = { Name = "${local.name}-data-${each.key}" }
}

# Firewall endpoints, used when enable_network_firewall is on.
resource "aws_subnet" "firewall" {
  for_each          = var.enable_network_firewall ? local.index : {}
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, 30 + each.value)
  tags              = { Name = "${local.name}-firewall-${each.key}" }
}

resource "aws_eip" "nat" {
  for_each = local.index
  domain   = "vpc"
}

resource "aws_nat_gateway" "main" {
  for_each      = local.index
  allocation_id = aws_eip.nat[each.key].id
  subnet_id     = aws_subnet.public[each.key].id
  depends_on    = [aws_internet_gateway.main]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# App subnets leave through the firewall when it's on, otherwise straight through NAT.
resource "aws_route_table" "app" {
  for_each = local.index
  vpc_id   = aws_vpc.main.id
}

resource "aws_route" "app_out" {
  for_each               = local.index
  route_table_id         = aws_route_table.app[each.key].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = var.enable_network_firewall ? null : aws_nat_gateway.main[each.key].id
  vpc_endpoint_id        = var.enable_network_firewall ? local.firewall_endpoints[each.key] : null
}

resource "aws_route_table_association" "app" {
  for_each       = aws_subnet.app
  subnet_id      = each.value.id
  route_table_id = aws_route_table.app[each.key].id
}

resource "aws_route_table" "data" {
  vpc_id = aws_vpc.main.id
}

resource "aws_route_table_association" "data" {
  for_each       = aws_subnet.data
  subnet_id      = each.value.id
  route_table_id = aws_route_table.data.id
}

# AWS services are reached privately, so the firewall only has to allow the model provider.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [for t in aws_route_table.app : t.id]
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(["ecr.api", "ecr.dkr", "logs", "secretsmanager", "kms", "xray", "monitoring"])
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true
  subnet_ids          = [for s in aws_subnet.app : s.id]
  security_group_ids  = [aws_security_group.endpoints.id]
}
