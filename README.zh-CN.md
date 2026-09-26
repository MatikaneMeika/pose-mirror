# pose-mirror 🧍

对着摄像头摆个动作，自动找到姿势最像的参考图。

`pose-mirror` 是一个本地运行的画师开源工具：实时读取摄像头，用姿态估计识别你的身体动作，在参考图库里搜索姿势最相似的照片。不联网、不注册、不上传——所有计算都在你自己的电脑上完成。

[English](README.md)

## 下载（Windows，免装 Python）

去 [Releases 页面](https://github.com/MatikaneMeika/pose-mirror/releases)
下载 `pose-mirror.exe`，单独放一个文件夹里，双击运行。首次启动会自动
下载姿态模型（约 9 MB）到 exe 旁边，之后完全离线运行。然后在浏览器打开
http://127.0.0.1:8000。

> exe 由 GitHub Actions 在每次推送 `v*` 标签时自动构建
>（见 `.github/workflows/build.yml`）。

## 手机版（Android）

另有原生安卓客户端：
[pose-mirror-android](https://github.com/MatikaneMeika/pose-mirror-android)。
完全离线、独立运行——手机上用 CameraX + MediaPipe PoseLandmarker 实时识别姿态，
搜索同一套可移植索引格式。两端之间没有任何网络连接，唯一的共同点是索引文件
格式（`docs/INDEX_FORMAT.md`）。

## 快速开始

**Windows：** 双击 `install.bat`。
**Linux/macOS：** 运行 `bash setup.sh`。

脚本会检查 Python 3.10+、创建 `.venv`、装好所有依赖，最后打印接下来
三步命令。简述如下：

```bash
# 获取参考图（Wikimedia Commons，开放许可）
.venv/bin/python -m posemirror.crawl_wikimedia --limit 50

# 构建姿势索引（首次运行会自动下载 MediaPipe 模型）
.venv/bin/python -m posemirror.build_index

# 启动服务，浏览器打开 http://127.0.0.1:8000
.venv/bin/python -m posemirror.server
```

（Windows 下把 `.venv/bin/python` 换成 `.venv\Scripts\python`。）

站在摄像头能看到全身的位置，摆个动作，右侧就会实时刷出姿势最接近的
参考图。点击缩略图可以放大查看。

## 原理

```
摄像头画面 ──▶ MediaPipe PoseLandmarker ──▶ 33 个关节点
                        │
                        ▼
              归一化：以两髋中点为原点，
              以肩髋距离为尺度，
              展平 x/y → 66 维单位向量
                        │
                        ▼
        与索引向量做余弦相似度 ──▶ Top-K 匹配
```

- **姿态估计**：MediaPipe Tasks `PoseLandmarker`（full 模型）。模型文件首次
  运行时自动下载到 `models/`，已加入 `.gitignore`，不会提交到仓库。
- **归一化**（`src/posemirror/pose.py`）：平移不变（髋中点为原点）、尺度不变
  （肩髋距离；退化时用最大关节点间距）。v1 只用 x/y，z（深度）通道是后续工作。
- **匹配**：单位向量余弦相似度。一张图有多人时保留平均可见度最高的那个；
  可见关节点不足 50% 的图片在建索引时跳过。
- **镜像开关**：匹配前把查询姿势水平翻转，适合参考图朝向相反的情况。
- **服务**：FastAPI + 后台 OpenCV 采集线程。浏览器 UI 是纯 HTML/JS，不跑
  模型、不依赖 CDN：MJPEG `<img>` 显示带骨骼的实时画面，轮询 `/api/matches`
  刷新匹配结果。

## 数据来源

| 来源 | 方式 | 许可说明 |
|---|---|---|
| Wikimedia Commons | `crawl_wikimedia` —— 礼貌爬取（真实 UA，约 1 请求/秒） | 每张图的作者与许可写入索引 manifest |
| quickposes.com | 手动下载（无稳定公开 API，见模块 docstring）→ 放到 `data/raw/quickposes/` | 仅个人学习使用 |
| 自己的照片 | 直接丢进 `data/raw/`（子目录随意） | 你自己的图 |

所有下载的图片都在 `data/` 下，已加入 `.gitignore`。**不要把下载的图片
或模型提交到仓库。**

## 目录结构

```
pose-mirror/
├── src/posemirror/
│   ├── pose.py             # 模型下载、姿态提取、归一化、相似度
│   ├── crawl_wikimedia.py  # Commons API 爬虫（礼貌，记录许可信息）
│   ├── crawl_quickposes.py # 文档化 stub → 手动下载流程
│   ├── build_index.py      # 扫描 data/raw/** → embeddings.npz + manifest + 缩略图
│   │                       # + format.json（索引格式 v1，见 docs/INDEX_FORMAT.md）
│   ├── export_portable.py  # 索引 → 无依赖 bundle，用于 GitHub Release
│   └── server.py           # FastAPI：/（UI）、/api/stream、/api/matches、/api/search、/api/status
├── web/                    # 深色画师风 UI（无需构建，响应式）
├── docs/
│   └── INDEX_FORMAT.md     # 与安卓客户端共享的索引格式规范
├── data/                   # 已忽略：原始图片 + 索引
└── models/                 # 已忽略：MediaPipe 模型
```

## 接口

- `GET /` —— 界面
- `GET /api/stream` —— 带骨骼的 MJPEG 摄像头流（无摄像头时返回 503）
- `GET /api/matches?k=9&mirror=0` —— JSON Top-K 匹配结果
- `POST /api/search` —— JSON `{"landmarks": [[x,y],...]（33 对）,
  "mirror": false, "top_k": 9}`，对客户端传来的姿势做无状态匹配
  （给脚本、测试或第三方客户端用）。图片数据不经过网络，不属于移动端架构。
- `GET /api/status` —— `{"camera_ok": bool, "index_size": int, ...}`
- `GET /thumbs/{id}.jpg` —— 缩略图静态文件

## 路线图

- [ ] 安卓 App（原生 Kotlin）：CameraX + MediaPipe Tasks PoseLandmarker
      for Android。完全离线、完全独立运行——不与 PC 通信。复用同一套索引数据：
      在 PC 上构建一次，用 `python -m posemirror.export_portable` 导出，
      作为 GitHub Release 附件发布，App 下载后直接使用。归一化与匹配算法
      见 `docs/INDEX_FORMAT.md`（纯伪代码、无特殊依赖），Kotlin 端可逐行对照实现。
- [ ] 姿势向量加入 z（深度）通道（需要索引格式 v2）。
- [ ] VIDEO 模式 + 跟踪，让实时匹配更平滑。
- [ ] 基于 manifest 的关键词搜索。

## 参与贡献

欢迎 PR。保持纯 Python、不在 JS 里跑模型、不依赖 CDN。注释与 docstring
用英文。改完跑一下 `python -m py_compile`。
