# ============================================================================
# 容器编排：CCE 集群 + 节点池
# 网关 = Deployment + Service（常驻），清单见 src/k8s/
# 集群规格 / 节点规格 / 台数 / 磁盘均显式指定。
# ============================================================================

resource "huaweicloud_cce_cluster" "main" {
  name                   = "${var.project_name}-cce"
  cluster_type           = "VirtualMachine"
  flavor_id              = var.cce_cluster_flavor
  vpc_id                 = huaweicloud_vpc.main.id
  subnet_id              = huaweicloud_vpc_subnet.main.id
  container_network_type = "vpc-router"
  # 管理面公网入口：便于本地 kubectl 管理集群
  eip        = huaweicloud_vpc_eip.cce.address
  custom_san = [huaweicloud_vpc_eip.cce.address]
}

resource "huaweicloud_vpc_eip" "cce" {
  publicip {
    type = "5_bgp"
  }
  bandwidth {
    name        = "${var.project_name}-cce-bw"
    size        = 5
    share_type  = "PER"
    charge_mode = "traffic"
  }
}

resource "huaweicloud_cce_node_pool" "main" {
  cluster_id         = huaweicloud_cce_cluster.main.id
  name               = "${var.project_name}-nodepool"
  flavor_id          = var.cce_node_flavor
  initial_node_count = var.cce_node_count
  availability_zone  = "${var.region}a"
  subnet_id          = huaweicloud_vpc_subnet.main.id
  os                 = "Huawei Cloud EulerOS 2.0"
  password           = var.node_password
  runtime            = "containerd"

  root_volume {
    size       = 50
    volumetype = "SSD"
  }

  data_volumes {
    size       = 100
    volumetype = "SSD"
  }

  lifecycle {
    # 节点数由运行期人工/自动扩缩维护，不让 apply 回滚
    ignore_changes = [initial_node_count]
  }
}
