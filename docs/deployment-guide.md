# 部署指导书

## 前置条件

1. 华为云账号，目标区域 `cn-north-4`（北京四），已开通 CCE / SWR / ELB / EIP 服务。
2. 本地已安装：
   - `terraform`（≥1.5）
   - `docker`（构建镜像）
   - `kubectl`（管理 CCE 集群）
   - `huaweicloud` CLI 或控制台访问权限（管理 SWR / CCE）
3. **MaaS 预置模型服务已开通**（控制台 ModelArts → 预置服务，勾选服务声明并免费开通），并已创建 **API Key**（控制台「API Key 管理」创建，只显示一次，妥善保存）。
   - 说明：MaaS 预置服务当前仅部分区域可用（西南-贵阳一 / 华北-乌兰察布一 / 中国香港）；网关可部署在 `cn-north-4`，模型调用走公网 API，不影响。
4. 环境变量配置凭据（不硬编码）：
   ```bash
   export HW_ACCESS_KEY="<your-access-key>"
   export HW_SECRET_KEY="<your-secret-key>"
   ```

## 第一步：创建基础设施

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# 编辑 terraform.tfvars，填写 node_password 等
terraform init
terraform plan
terraform apply -auto-approve
```

预期输出：`Apply complete!`，输出中包含 `swr_image`（镜像地址）。

## 第二步：构建并推送网关镜像

```bash
cd ../src
# 登录 SWR（token 会过期，需在控制台/CLI 获取临时登录指令）
docker build -t swr.cn-north-4.myhuaweicloud.com/<organization>/model-access-gateway:latest .
docker push swr.cn-north-4.myhuaweicloud.com/<organization>/model-access-gateway:latest
```

> `<organization>` 与 `terraform.tfvars` 中的 `swr_organization` 保持一致。

## 第三步：配置 K8s Secret 并部署网关

```bash
cd ../src/k8s
# 编辑 secret.yaml，填入：
#   API_KEY      —— 网关对外 API Key（客户端访问 /api/v1 时使用）
#   MAAS_API_KEY —— MaaS API Key（控制台创建）
kubectl apply -f secret.yaml

# 部署 Deployment 与 Service（Service 自动创建公网 ELB + EIP）
cd ../k8s
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml

# 等待 Pod 就绪
kubectl get pods -w
# 获取公网访问地址
kubectl get svc gateway
```

预期输出：`gateway` Service 的 `EXTERNAL-IP` 即为公网入口，访问地址为 `http://<EXTERNAL-IP>/api/v1`。

## 第四步：验证

按 README「使用方法/验证」章节执行验证命令（curl 健康检查、models、chat、embeddings、流式）。

## 清理资源

```bash
# 删除 K8s 资源（含自动创建的 ELB/EIP）
kubectl delete -f src/k8s/

# 销毁基础设施（CCE 集群、节点、SWR、VPC）
cd infra
terraform destroy -auto-approve
```
