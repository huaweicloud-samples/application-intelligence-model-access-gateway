# 基础镜像：国内可直接拉取的 daocloud 镜像源（Docker Hub 在国内网络不通）
FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app

# 使用华为云 pip 镜像源加速依赖安装
COPY requirements.txt .
RUN pip3 install -r requirements.txt -U --no-cache-dir \
    -i https://mirrors.huaweicloud.com/repository/pypi/simple

COPY ./api ./api

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
