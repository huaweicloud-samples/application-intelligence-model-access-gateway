# ============================================================================
# 输出
# ============================================================================

output "cce_cluster_id" {
  description = "CCE 集群 ID"
  value       = huaweicloud_cce_cluster.main.id
}

output "swr_image" {
  description = "网关镜像地址（构建后 push 到此地址）"
  value       = "swr.${var.region}.myhuaweicloud.com/${huaweicloud_swr_organization.main.name}/${huaweicloud_swr_repository.gateway.name}"
}

output "deployment_hint" {
  description = "部署提示"
  value       = "构建镜像并推送 SWR 后，执行 kubectl apply -f ../src/k8s/ 完成网关部署；Service 自动创建公网 ELB，访问地址见 Service 的 EXTERNAL-IP"
}
