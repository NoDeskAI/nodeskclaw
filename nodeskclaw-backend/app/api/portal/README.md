# Portal API 路由

Portal（用户门户）专用的 API 路由模块，与 Admin 路由完全独立。

## 目录结构

| 文件 | 职责 |
|------|------|
| `instances.py` | 实例 CRUD（内置 InstanceMember 权限检查） |
| `deploy.py` | 部署（创建实例 / 预检 / 取消 / 进度 SSE） |
| `channel_configs.py` | Channel 配置读写（内置权限检查） |
| `mcp.py` | MCP 服务器管理（内置权限检查） |
| `instance_members.py` | 实例成员管理（新功能） |

## 与 Admin 路由的区别

- Portal 路由内置实例级权限检查（基于 `InstanceMember` 模型）
- Admin 路由基于组织角色（`AdminMembership`），不做实例级权限检查
- 两套路由共用底层 service 层
