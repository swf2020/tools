# Docker Overlay网络VXLAN封装技术文档

## 1. 概述

Docker Overlay网络使用VXLAN（Virtual Extensible LAN）技术实现跨主机的容器通信。VXLAN是一种网络虚拟化技术，通过在现有网络基础设施上创建逻辑二层网络，解决传统VLAN ID数量限制（4096个）的问题。

## 2. 架构组成

### 2.1 核心组件
- **VXLAN隧道端点（VTEP）**：负责VXLAN封装/解封装
- **VXLAN网络标识符（VNI）**：24位标识符，支持1600万个虚拟网络
- **外部UDP封装**：使用4789端口（IANA分配）
- **分布式控制平面**：Docker Swarm模式使用gossip协议

### 2.2 Docker Overlay网络架构
```
+-------------------------------------------------------+
|                  应用程序容器                         |
+-------------------------------------------------------+
|                Sandbox (网络命名空间)                |
+-------------------------------------------------------+
|       veth pair       |       veth pair       | ...  |
+-------------------------------------------------------+
|          br0 (Linux网桥) - docker_gwbridge            |
+-------------------------------------------------------+
|          eth0 (物理网卡) - 外部UDP封装                |
+-------------------------------------------------------+
|                   物理网络基础设施                    |
+-------------------------------------------------------+
```

## 3. VXLAN封装机制

### 3.1 封装格式
```
+-----------------------------------------------+
|                原始以太网帧                    |
+-----------------------------------------------+
|   外部UDP头部 (源端口: 随机, 目的端口: 4789)   |
+-----------------------------------------------+
|           外部IP头部 (主机IP地址)              |
+-----------------------------------------------+
|          外部以太网头部 (主机MAC)              |
+-----------------------------------------------+
```

### 3.2 关键字段说明
- **VXLAN头部**：8字节，包含：
  - Flags（8位）：其中I位=1表示有效VNI
  - 保留字段（24位）
  - VNI（24位）：虚拟网络标识符
  - 保留字段（8位）

- **UDP头部**：
  - 源端口：由内核随机选择
  - 目的端口：固定4789
  - 校验和：可配置开启/关闭

## 4. 工作流程

### 4.1 网络创建
```bash
# 创建overlay网络
docker network create -d overlay --subnet 10.0.0.0/24 my-overlay

# Swarm模式下
docker network create \
  --driver overlay \
  --subnet 10.0.0.0/24 \
  --gateway 10.0.0.1 \
  my-overlay-net
```

### 4.2 数据包转发流程
1. **容器发送数据包**
   - 容器内应用产生IP数据包
   - 通过veth pair到达Linux网桥

2. **VXLAN封装**
   - Docker daemon检查目的IP
   - 查询overlay网络映射表
   - 添加VXLAN头部（包含VNI）
   - 外层封装UDP/IP/以太网头部

3. **跨主机传输**
   - 通过物理网络传输到目标主机
   - 目标VTEP接收并解封装
   - 根据VNI转发到对应容器

### 4.3 ARP解析优化
Docker使用分布式控制平面维护IP-MAC-VTEP映射，避免传统ARP广播：
- 每个节点维护全局映射表
- 使用gossip协议同步状态
- 减少overlay网络中的广播流量

## 5. 配置参数

### 5.1 网络创建选项
```bash
docker network create \
  --driver overlay \
  --subnet 10.0.0.0/24 \
  --gateway 10.0.0.1 \
  --opt encrypted=true \          # 启用加密
  --opt com.docker.network.driver.mtu=1450 \  # 设置MTU
  my-secure-overlay
```

### 5.2 重要配置参数
| 参数 | 默认值 | 说明 |
|------|--------|------|
| com.docker.network.driver.overlay.vxlanid_list | 自动分配 | VNI范围 |
| com.docker.network.driver.mtu | 1450 | 建议MTU值 |
| encrypted | false | IPSec加密 |

## 6. 性能优化

### 6.1 MTU调整
```bash
# 计算建议MTU值
物理网络MTU - VXLAN封装开销 = 建议MTU
1500 - 50 = 1450 bytes
```

### 6.2 内核参数优化
```bash
# 增加VXLAN套接字缓冲区
sysctl -w net.core.rmem_max=26214400
sysctl -w net.core.wmem_max=26214400

# 开启UDP校验和卸载（如果网卡支持）
ethtool -K eth0 tx-udp_tnl-csum-segmentation on
```

### 6.3 加密性能考虑
- 启用encrypted选项会增加CPU开销
- 建议在可信网络环境中关闭加密
- 考虑硬件加速方案

## 7. 故障排查

### 7.1 常用诊断命令
```bash
# 查看网络信息
docker network inspect my-overlay

# 检查VXLAN接口
ip -d link show

# 查看路由表
ip route show

# 查看ARP/NDP缓存
ip neigh show

# 抓包分析
tcpdump -i eth0 udp port 4789 -vv
```

### 7.2 常见问题及解决

**问题1：容器间通信失败**
- 检查防火墙规则
- 验证4789端口是否开放
- 确认所有节点网络时间同步

**问题2：MTU相关问题**
```bash
# 测试MTU
ping -M do -s 1472 -c 4 <目标IP>

# 临时调整MTU
ip link set dev eth0 mtu 9000
```

**问题3：加密配置问题**
```bash
# 检查IPSec状态
sudo ip xfrm state
sudo ip xfrm policy
```

## 8. 安全考虑

### 8.1 网络安全
1. **网络隔离**：不同overlay网络默认隔离
2. **加密传输**：支持IPSec加密
3. **访问控制**：可与Docker Swarm服务发现结合

### 8.2 最佳实践
- 在生产环境启用网络加密
- 定期更新Swarm集群加密密钥
- 监控网络流量异常
- 使用网络策略限制容器通信

## 9. 监控与日志

### 9.1 监控指标
- VXLAN隧道状态
- 丢包率统计
- 带宽使用情况
- 封装/解封装性能

### 9.2 日志收集
```bash
# Docker daemon日志
journalctl -u docker.service

# 内核日志（VXLAN相关）
dmesg | grep vxlan
```

## 10. 限制与注意事项

### 10.1 技术限制
- 需要Linux内核3.7+（推荐4.0+）
- 所有节点需开放UDP 4789端口
- 某些云服务商可能限制VXLAN流量

### 10.2 性能影响
- VXLAN封装增加约50字节开销
- 软件封装消耗CPU资源
- 大规模部署需考虑控制平面压力

### 10.3 兼容性考虑
- 与传统VLAN网络共存
- 多厂商网络设备支持
- 混合云环境部署

## 附录A：相关命令参考

```bash
# 完整创建overlay网络示例
docker network create \
  --driver overlay \
  --attachable \
  --subnet 10.10.0.0/16 \
  --subnet 2001:db8::/64 \
  --opt encrypted=true \
  --opt com.docker.network.driver.mtu=1450 \
  production-net

# 服务连接到overlay网络
docker service create \
  --name web \
  --network production-net \
  --publish published=80,target=80 \
  nginx:latest
```

## 附录B：VXLAN封装开销计算

```
总封装开销 = 外部以太网头(14) + IP头(20) + UDP头(8) + VXLAN头(8) = 50字节
有效载荷MTU = 物理MTU - 封装开销
举例：1500 - 50 = 1450字节
```

---

*文档版本：1.0*
*最后更新：2024年*
*适用Docker版本：20.10+*