# EchoWrt-Rockchip

EchoWrt-Rockchip 是面向 Rockchip 设备的 ImmortalWrt 固件构建与独立维护项目。本仓库保存构建配置、定制脚本和 GitHub Actions 工作流，不再维护一份完整且长期分叉的 OpenWrt 源码树。

## 源码策略

- 主线源码：[ImmortalWrt openwrt-25.12](https://github.com/immortalwrt/immortalwrt/tree/openwrt-25.12)
- 构建配置：本仓库的 immortalwrt/rockchip/defconfig
- 老设备移植参考：[DHDAXCW/lede-rockchip](https://github.com/DHDAXCW/lede-rockchip)

旧 lede-rockchip 不再作为日常构建源。每次构建产物都会附带 BUILD_INFO.txt 和 COMMUNITY_SOURCES.txt，记录实际使用的源码提交与第三方软件包提交，便于复现和排查。

## 当前默认构建设备

以下列表与 immortalwrt/rockchip/defconfig 保持一致：

~~~
armsom_sige3
armsom_sige7
friendlyarm_nanopc-t4
friendlyarm_nanopc-t6
friendlyarm_nanopi-r3s
friendlyarm_nanopi-r4se
friendlyarm_nanopi-r5c
friendlyarm_nanopi-r5s
friendlyarm_nanopi-r6c
friendlyarm_nanopi-r6s
radxa_rock-5a
radxa_rock-5b
xunlong_orangepi-5
xunlong_orangepi-5-plus
~~~

ImmortalWrt 25.12 已有定义、但默认配置暂未启用的设备包括 NanoPi R2C、R2S 和 R4S。它们只需加入构建矩阵并完成实机验证。

DoorNet、LubanCat 和部分 Hinlink 设备不在当前官方 25.12 Rockchip 设备定义中，不能只复制旧配置直接发布；这些设备需要单独移植 DTS、镜像布局、网络接口和升级脚本，并保留串口救砖方案。

## 云编译

1. Fork 本仓库。
2. 打开 GitHub 的 Actions 页面。
3. 选择 **Build EchoWrt Rockchip firmware**。
4. 点击 **Run workflow**，选择：
   - **profile**：standard 或 docker
   - **source_ref**：默认 openwrt-25.12，也可指定经过验证的 tag 或 commit
   - **publish_release**：实机验证前建议保持关闭
5. 构建完成后先下载 Artifact 验证；确认无误后再发布 Release。

工作流使用 GitHub 托管的 Ubuntu 22.04 runner，不依赖原作者的 self-hosted runner。

## 默认访问

- 用户名：root
- 初始密码：不预置，首次登录时设置
- 管理地址：192.168.8.1
- 默认主机名：EchoWrt

首次从可信 LAN 打开 LuCI 后，请立即进入密码设置页面设置强密码；也可以通过 SSH 执行 passwd。完成密码设置前不要把设备暴露到公网。

## 产物校验

每个 Artifact 或 Release 应至少包含：

- BUILD_INFO.txt：主源码、分支、提交和工作流提交
- COMMUNITY_SOURCES.txt：第三方软件包仓库与提交
- SHA256SUMS：所有 img.gz 镜像的校验值
- 对应设备的固件镜像与构建元数据

刷机前请核对设备型号和镜像文件名。EMMC/SD 刷写参考见 [data/emmc.md](data/emmc.md)，其中包含高风险磁盘写入命令，执行前必须再次确认目标块设备。

## 维护路线

维护和发布门槛见 [docs/MAINTENANCE.md](docs/MAINTENANCE.md)。近期顺序是：

1. 稳定官方 ImmortalWrt 25.12 云编译。
2. 固定并周期性更新第三方软件包版本。
3. 用实机建立设备验收矩阵。
4. 按优先级移植旧源码树中的遗留设备。

## 致谢与许可

感谢 [OpenWrt](https://github.com/openwrt/openwrt)、[ImmortalWrt](https://github.com/immortalwrt/immortalwrt)、[P3TERX/Actions-OpenWrt](https://github.com/P3TERX/Actions-OpenWrt) 以及相关设备和软件包维护者。

本仓库按 [GPL-3.0](LICENSE) 发布。第三方源码和二进制仍分别受其自身许可证约束。
