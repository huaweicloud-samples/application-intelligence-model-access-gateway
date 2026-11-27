import os, hashlib, hmac, datetime, json, requests

ak = os.environ["CLOUD_SDK_AK"]
sk = os.environ["CLOUD_SDK_SK"]
project_id = "019f5e77771f74b3a4a2d9e1f906fb9c"
cluster_id = "8ad21247-9d08-11f1-9df7-0255ac10004e"
host = "cce.cn-southwest-2.myhuaweicloud.com"
resource = f"/api/v3/projects/{project_id}/clusters/{cluster_id}/longaksk/config"
req_path = resource          # 实际请求（无斜杠）
canonical_path = resource + "/"  # 网关验签规范成带斜杠


def sign(method, canon_path, payload_str):
    signed_headers = "host;x-sdk-date"
    now = datetime.datetime.utcnow()
    date_str = now.strftime("%Y%m%dT%H%M%SZ")
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()
    canonical_headers = f"host:{host}\nx-sdk-date:{date_str}\n"
    canonical_request = (
        f"{method}\n{canon_path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )
    str_to_sign = (
        f"SDK-HMAC-SHA256\n{date_str}\n"
        f"{hashlib.sha256(canonical_request.encode()).hexdigest()}"
    )
    signature = hmac.new(sk.encode(), str_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"SDK-HMAC-SHA256 Access={ak}, SignedHeaders={signed_headers}, Signature={signature}"
    return auth, date_str, host


url = f"https://{host}{req_path}"

# 1) POST 上传长期 AK/SK
body = {
    "apiVersion": "v3",
    "kind": "LongAKSK",
    "metadata": {"name": cluster_id},
    "spec": {"identity": {"longAkSk": {"ak": ak, "sk": sk}}},
}
payload_str = json.dumps(body)
auth, date_str, _ = sign("POST", canonical_path, payload_str)
headers = {
    "host": host,
    "x-sdk-date": date_str,
    "Authorization": auth,
    "Content-Type": "application/json",
}
r = requests.post(url, headers=headers, data=payload_str, timeout=30)
print("POST", r.status_code, r.text[:400])

# 2) GET 取 kubeconfig
if r.status_code in (200, 202):
    auth2, date_str2, _ = sign("GET", canonical_path, "")
    headers2 = {"host": host, "x-sdk-date": date_str2,
                "Authorization": auth2}
    g = requests.get(url, headers=headers2, timeout=30)
    print("GET", g.status_code, "len", len(g.text))
    if g.status_code == 200 and "server:" in g.text:
        out = r"D:\workbuddy\kubeconfig-cn-southwest-2-gateway.yaml"
        with open(out, "w", encoding="utf-8") as f:
            f.write(g.text)
        print("kubeconfig 写入:", out)
        for line in g.text.splitlines():
            if "server:" in line:
                print("   server:", line.strip())
    else:
        print("GET body:", g.text[:300])
