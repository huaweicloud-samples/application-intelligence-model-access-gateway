variable "region" {
  description = "华为云区域"
  type        = string
  default     = "cn-north-4"
}

variable "project_name" {
  description = "项目名称，用于资源命名前缀"
  type        = string
  default     = "maas-gateway"
}

variable "cce_cluster_flavor" {
  description = "CCE 集群规格"
  type        = string
  default     = "cce.s1.small"
}

variable "cce_node_flavor" {
  description = "CCE 节点规格"
  type        = string
  default     = "c7.large.2"
}

variable "cce_node_count" {
  description = "CCE 节点初始数量"
  type        = number
  default     = 1
}

variable "node_password" {
  description = "CCE 节点登录密码（部署时通过 tfvars/环境变量传入，不硬编码）"
  type        = string
  sensitive   = true
}

variable "swr_organization" {
  description = "SWR 镜像仓库组织名"
  type        = string
  default     = "maas-gateway"
}
