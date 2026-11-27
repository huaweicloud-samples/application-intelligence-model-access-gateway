# ============================================================================
# 容器镜像仓库：SWR 组织 + 仓库
# ============================================================================

resource "huaweicloud_swr_organization" "main" {
  name = var.swr_organization
}

resource "huaweicloud_swr_repository" "gateway" {
  organization = huaweicloud_swr_organization.main.name
  name         = "model-access-gateway"
  description  = "AI model access gateway"
  is_public    = false
}
