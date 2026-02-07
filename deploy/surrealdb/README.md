# SurrealDB 部署指南

Memory 系统使用 SurrealDB 作为持久化图存储后端（替代 Neo4j）。

## 快速启动

```bash
cd deploy/surrealdb

# 设置密码（可选，默认 root/root）
export SURREALDB_USER=root
export SURREALDB_PASSWORD=your_secure_password

# 启动
docker-compose up -d
```

## 访问

- **HTTP API**: http://localhost:8000
- **WebSocket RPC**: ws://localhost:8000/rpc
- 默认用户名: `root`
- 默认密码: `root`（或你设置的 `SURREALDB_PASSWORD`）

## 配置 Cloud Backend

启动 SurrealDB 后，确认 `src/cloud_backend/config/cloud-backend.yaml` 中的配置：

```yaml
graph_store:
  backend: surrealdb
  url: ws://localhost:8000/rpc
  namespace: ami
  database: memory
  username: root
  password: your_secure_password  # 与上面设置的一致
  vector_dimensions: 1024
```

或使用环境变量：

```bash
export SURREALDB_URL=ws://localhost:8000/rpc
export SURREALDB_NAMESPACE=ami
export SURREALDB_DATABASE=memory
export SURREALDB_USER=root
export SURREALDB_PASSWORD=your_secure_password
```

## 验证

重启 Cloud Backend 后，检查日志确认连接成功：

```bash
tail -f ~/ami-server/logs/cloud-backend.log | grep -i surrealdb
```

## 数据管理

```bash
# 通过 HTTP API 查询数据
curl -X POST http://localhost:8000/sql \
  -H "Accept: application/json" \
  -u "root:your_password" \
  -d "USE NS ami DB memory; SELECT count() FROM state GROUP ALL;"

# 停止
docker-compose down

# 清空数据重建
docker-compose down -v
docker-compose up -d
```

## 生产环境建议

1. 使用强密码（修改 `SURREALDB_PASSWORD`）
2. 数据持久化在 Docker Volume `surrealdb_data` 中（RocksDB 存储引擎）
3. 定期备份 Volume 数据
4. 如需 TLS，可在 SurrealDB 前置 Caddy/Nginx 反向代理
