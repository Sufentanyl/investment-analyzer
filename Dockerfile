# 保持 3.11 不变，兼容性最好
FROM python:3.11-slim

WORKDIR /app

# 只安装最基础的系统库
RUN apt-get update && apt-get install -y \
    build-essential \
    libxml2-dev \
    libxslt-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 升级 pip 并安装依赖
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 设置时区
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

CMD ["python", "-u", "src/main.py"]