# ============================================================================
# 网络：VPC + 子网 + 安全组
# ============================================================================

resource "huaweicloud_vpc" "main" {
  name = "${var.project_name}-vpc"
  cidr = "10.0.0.0/16"
}

resource "huaweicloud_vpc_subnet" "main" {
  name       = "${var.project_name}-subnet"
  vpc_id     = huaweicloud_vpc.main.id
  cidr       = "10.0.1.0/24"
  gateway_ip = "10.0.1.1"
}

# 节点安全组：出网放行（访问 MaaS 公网端点），入站 80 由 ELB 转发
resource "huaweicloud_networking_secgroup" "main" {
  name        = "${var.project_name}-sg"
  description = "Security group for ${var.project_name}"
}

resource "huaweicloud_networking_secgroup_rule" "allow_egress" {
  direction         = "egress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  remote_ip_prefix  = "0.0.0.0/0"
  security_group_id = huaweicloud_networking_secgroup.main.id
}
