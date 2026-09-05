# 维护与发布约定

## 1. 源码决策

在 2026-08-27 的接管审计中：

- README 指向的 lede-rockchip 是旧式完整源码分叉，不适合继续承担主线更新。
- 原工作流实际使用 DHDAXCW/immortalwrt 的 openwrt-24.10 分支，而不是 README 中的源码地址。
- 该 fork 当时相对 ImmortalWrt 官方分支落后 154 个提交；其领先提交主要是 QNAP/QHora 支持，与 Rockchip 默认镜像无关。
- 两个分支当时的 target/linux/rockchip/image/armv8.mk 设备定义一致。

接管后进一步核对官方发布线，当前最新稳定分支为 openwrt-25.12，最新稳定标签为 v25.12.1。因此主线跟随 ImmortalWrt 官方 openwrt-25.12；旧 lede-rockchip 只用于查找遗留设备补丁，不能直接作为新 Release 的可信来源。

25.12 已在官方 feeds 提供 Go、v2ray-geodata、Argon、AdGuardHome、libmbim 和大量代理依赖。构建优先使用官方版本，避免旧仓库重复定义或反向降级；仅保留官方缺少的社区应用。MosDNS 是例外：为保证 LuCI 与后端配套，使用固定提交的完整扩展替换官方基础包。

社区仓库按子目录白名单导入，不能把整个仓库无条件放进 package/。5G 支持只保留 HyperModem 与其 PCIe MHI 驱动，使用官方 feeds 的 quectel-cm；旧 luci-app-modem 因依赖 25.12 已不存在的 ndisc6/rdisc6，完成移植前不进入默认镜像。Nikki 只导入前端和服务本体，统一使用 Helloworld 的稳定 Mihomo 包，避免 alpha/meta 变体互相冲突。

旧 Alist 配置迁移为官方维护的 OpenList；已不存在或已被替代的 luci-app-socat、v2dat 和 quectel-CM-5G 配置不再保留。新增旧插件前必须先确认 25.12 分支有可维护的软件包来源。

## 2. 分支策略

- main：只保留已通过云编译和至少一台实机冒烟测试的改动。
- maintenance/*：构建系统、依赖和文档维护。
- device/<设备名>：单设备移植；在验证前不进入默认多设备配置。
- legacy/*：只用于保存旧源码分析或临时移植，不发布为主线固件。

## 3. 发布门槛

候选固件依次通过以下阶段：

1. 仓库校验：Shell 语法、工作流 action 固定版本、设备清单一致，以及发布流程回归测试。standard 和 docker 均需通过完整配置解析检查。
2. 云编译：standard 配置完整成功，产物包含三份追溯文件。
3. 镜像检查：镜像与请求设备及 profiles.json 一致；FIRMWARE_SHA256SUMS 不含重复或越界文件名，且完整覆盖每个镜像；逐个 SHA256 验证通过。
4. 实机冒烟：启动、LAN/WAN、存储、重启和升级路径正常。
5. 发布：使用独立日期与 profile 标签，绑定实际构建配置提交；先创建草稿，完整上传并核对全部附件名称、大小与 SHA256 后再公开。Release 中注明源码提交和已验证设备。

公开 Release 不允许覆盖附件。失败后可重跑以继续同一提交的草稿；已有附件必须与本地产物一致，否则停止并人工检查，不能通过覆盖掩盖冲突。若 GitHub 拒绝在指定提交创建标签，应先处理所需仓库权限，不得退回默认分支创建错误标签。

docker profile 在 standard 通过后单独验证，不能替代 standard 基线。

25.12 的官方 Dockerman 使用 `ucode-mod-socket`，不再要求旧的 `luci-lib-docker`；docker.config 必须与官方应用依赖保持一致，不能仅依赖 make defconfig 静默丢弃失效选项。

## 4. 实机冒烟清单

每种设备至少记录：

- 设备全名、SoC、RAM、启动介质和硬件版本。
- 串口或系统启动日志，无持续崩溃、内核异常或只读根文件系统。
- 192.168.8.1 管理地址可达，首次登录可设置 root 密码，固件不含预置密码。
- 所有 LAN/WAN 接口名称、MAC 地址和链路速率正确。
- DHCP、DNS、NAT 和 IPv6（若启用）正常。
- 冷启动、软重启各三次。
- 备份恢复和 sysupgrade 路径验证；首次验证前准备可用的救砖方法。
- 风扇、LED、Wi-Fi、USB、NVMe、SATA、5G 模组等板级功能按硬件逐项测试。

建议把 BUILD_INFO.txt、COMMUNITY_SOURCES.txt、FIRMWARE_SHA256SUMS、新构建的 REQUESTED_CONFIG / RESOLVED_CONFIG 和关键日志附到对应 Issue。

## 5. 源码与软件包更新

- 主源码更新和第三方软件包更新分开提交，避免一次变更多个故障面。
- 第三方仓库由 immortalwrt/community-sources.lock 固定到准确 commit；更新时逐项修改并单独提交。
- 每次构建记录解析后的提交；已发布固件必须能定位到准确 commit。
- 先更新主源码并完成 standard 构建，再分批更新代理、主题、商店、5G 和其他社区软件包。
- 出现编译故障时，先根据 COMMUNITY_SOURCES.txt 回退单个软件包，不整体回退主源码。
- 每月至少检查一次 openwrt-25.12 安全更新；重大内核或网络栈更新必须重新跑实机矩阵。

## 6. Issue 分类

- build：依赖、下载、编译或 Actions 故障。
- device：设备启动、网口、存储、LED、风扇等板级问题。
- package：LuCI 或第三方软件包问题。
- release：文件缺失、校验、命名或升级问题。
- docs：设备清单、默认配置和刷机说明不一致。

故障报告若缺少设备型号、BUILD_INFO.txt 中的提交和复现步骤，应先补齐信息再进入修复。
