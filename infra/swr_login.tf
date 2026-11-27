# 生成 SWR 临时登录指令（docker login），供构建镜像推送使用
resource "huaweicloud_swr_temporary_login_command" "local" {
  enhanced = true
}

output "swr_login" {
  description = "SWR docker login 指令（执行即可登录）"
  value       = huaweicloud_swr_temporary_login_command.local.x_swr_docker_login
}
