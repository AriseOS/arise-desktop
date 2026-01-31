# Neo4j 部署指南

Memory 系统使用 Neo4j 作为持久化图存储后端。

## 快速启动

```bash
cd deploy/neo4j

# 设置密码（可选，默认 ami_password）
export NEO4J_PASSWORD=your_secure_password

# 启动
docker-compose up -d
```

## 访问

- **Browser UI**: http://localhost:7474
- **Bolt 连接**: neo4j://localhost:7687
- 默认用户名: `neo4j`
- 默认密码: `ami_password`（或你设置的 `NEO4J_PASSWORD`）

## 配置 Cloud Backend

启动 Neo4j 后，修改 `src/cloud_backend/config/cloud-backend.yaml`:

```yaml
graph_store:
  backend: neo4j  # 改为 neo4j
  uri: neo4j://localhost:7687
  user: neo4j
  password: your_secure_password  # 与上面设置的一致
  database: neo4j
```

或使用环境变量:

```bash
export NEO4J_URI=neo4j://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_secure_password
```

## 验证

重启 Cloud Backend 后，检查日志确认连接成功:

```bash
tail -f ~/ami-server/logs/cloud-backend.log | grep -i neo4j
```

## 数据管理

```bash
# 查看数据
docker exec -it ami-neo4j cypher-shell -u neo4j -p your_password "MATCH (n) RETURN labels(n), count(n)"

# 备份
docker exec ami-neo4j neo4j-admin database dump neo4j --to-path=/data/backup

# 停止
docker-compose down

# 清空数据重建
docker-compose down -v
docker-compose up -d
```

## 生产环境建议

1. 使用强密码
2. 配置 SSL/TLS
3. 定期备份
4. 监控内存使用（默认 heap 512MB，可在 docker-compose.yml 中调整）
