# 部署和启动脚本

本目录包含项目的部署、测试和启动脚本。

## 📁 脚本列表

### Linux/Mac 脚本

| 脚本 | 功能 | 用法 |
|------|------|------|
| `deploy-test.sh` | 自动化部署测试 | `bash deploy-test.sh` |
| `start-frontend.sh` | 启动前端开发服务器 | `bash start-frontend.sh` |
| `check-status.sh` | 检查服务状态 | `bash check-status.sh` |

### Windows 脚本

| 脚本 | 功能 | 用法 |
|------|------|------|
| `deploy-test.bat` | 自动化部署测试 | 双击运行或 `deploy-test.bat` |
| `start-frontend.bat` | 启动前端开发服务器 | 双击运行或 `start-frontend.bat` |

## 🚀 快速开始

### 方式 1: 使用部署脚本（推荐）

**Linux/Mac:**
```bash
cd scripts
bash deploy-test.sh
```

**Windows:**
```cmd
cd scripts
deploy-test.bat
```

### 方式 2: 手动启动

**后端服务:**
```bash
cd ..
python main.py
```

**前端服务:**
```bash
cd scripts
bash start-frontend.sh  # Linux/Mac
# 或
start-frontend.bat      # Windows
```

### 方式 3: Docker 部署

```bash
cd ..
docker-compose up -d
```

## 🔍 检查服务状态

```bash
cd scripts
bash check-status.sh
```

这将检查：
- 后端 API 服务 (http://localhost:8000)
- 前端服务 (http://localhost:5173)
- PostgreSQL 数据库
- Docker 容器状态

## ⚙️ 脚本配置

### deploy-test.sh / deploy-test.bat

该脚本会执行以下操作：
1. 检查依赖（Docker, Python, Node.js）
2. 启动 PostgreSQL 数据库（如果未运行）
3. 初始化数据库
4. 安装 Python 依赖
5. 启动后端服务
6. （可选）安装前端依赖并启动

### start-frontend.sh / start-frontend.bat

该脚本会：
1. 检查 Node.js 是否安装
2. 进入 frontend 目录
3. 安装依赖（如果需要）
4. 启动 Vite 开发服务器

### check-status.sh

该脚本会检查：
1. 后端 API 健康状态
2. 前端服务可访问性
3. 数据库连接状态
4. Docker 容器运行状态

## 🐛 故障排查

### 脚本无法执行（Linux/Mac）

```bash
chmod +x *.sh
```

### Windows 脚本被阻止

右键脚本 → 属性 → 解除锁定，或以管理员身份运行。

### 端口被占用

修改 `.env` 文件或 `docker-compose.yml` 中的端口配置。

## 📝 注意事项

1. **环境变量**: 确保项目根目录有 `.env` 文件
2. **依赖安装**: 首次运行前请确保已安装所有依赖
3. **权限问题**: Linux/Mac 下可能需要 `sudo` 执行 Docker 命令
4. **网络问题**: 确保能访问 Docker Hub 和 npm/pip 源

---

**最后更新**: 2026-04-18
