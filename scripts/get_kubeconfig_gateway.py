"""获取华为云项目 ID 与 CCE kubeconfig（SDK-HMAC 签名，无第三方依赖）"""
import os, hashlib, hmac, datetime, json, requests

ak = os.environ["CLOUD_SDK_AK"]
sk = os.environ["CLOUD_SDK_SK"]
region = os.environ.get("REGION", "cn-southwest-2")
cluster_id = os.environ["CCE_CLUSTER_ID"]


def sign(host, method, path, query="", body=""):
    now = datetime.datetime.utcnow()
    date_str = now.strftime("%Y%m%dT%H%M%SZ")
    payload_hash = hashlib.sha256(body.encode()).hexdigest()
    canonical_headers = f"host:{host}\nx-sdk-date:{date_str}\n"
    signed_headers = "host;x-sdk-date"
    # 网关验签时规范成带斜杠，签名必须匹配（旧脚本实证：CN 区域需 path + "/"）
    canonical_path = path + "/"
    canonical_request = (
        f"{method}\n{canonical_path}\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    str_to_sign = (
        f"SDK-HMAC-SHA256\n{date_str}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )
    signature = hmac.new(sk.encode(), str_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"SDK-HMAC-SHA256 Access={ak}, SignedHeaders={signed_headers}, Signature={signature}"
    return {"host": host, "x-sdk-date": date_str, "Authorization": auth}


# 1. 查 project_id
iam_host = "iam.myhuaweicloud.com"
headers = sign(iam_host, "GET", "/v3/projects", query="name=" + region)
resp = requests.get(f"https://{iam_host}/v3/projects?name={region}", headers=headers, timeout=30)
print("IAM projects HTTP", resp.status_code)
if resp.status_code != 200:
    print("ERR:", resp.text[:400])
    raise SystemExit(1)
projects = resp.json().get("projects", [])
project = next((p for p in projects if p["name"] == region), projects[0] if projects else None)
if not project:
    print("ERR: project not found")
    raise SystemExit(1)
project_id = project["id"]
print("project_id =", project_id, "name =", project["name"])

# 2. 获取 kubeconfig（longaksk 配置，含 AK/SK 凭证）
cce_host = f"cce.{region}.myhuaweicloud.com"
path = f"/api/v3/projects/{project_id}/clusters/{cluster_id}/longaksk/config"
headers = sign(cce_host, "GET", path)
resp = requests.get(f"https://{cce_host}{path}", headers=headers, timeout=30)
print("CCE kubeconfig HTTP", resp.status_code)
if resp.status_code != 200:
    print("ERR:", resp.text[:400])
    raise SystemExit(1)
body = resp.text
out = os.environ.get("KUBECONFIG_OUT", rf"D:\workbuddy\kubeconfig-{region}-gateway.yaml")
with open(out, "w", encoding="utf-8") as f:
    f.write(body)
print("kubeconfig 写入:", out)
for line in body.splitlines():
    if "server:" in line:
        print("   server:", line.strip())
