# 第三方组件与授权

建议本项目的自有源码、原创合成资料和页面截图使用仓库中的 MIT 文本。源码包不内嵌 Python 运行环境、浏览器、npm 模块、第三方模型权重或商业数据。安装依赖时各包携带自己的许可证；重新分发构建产物时也应保留相应声明。

| 组件 | 用途 | 已安装包的许可证标识 |
|---|---|---|
| FastAPI、Pydantic | API 与请求校验 | MIT |
| Uvicorn、httpx、python-dotenv | 本地服务、HTTP 客户端与配置 | BSD-3-Clause |
| pypdf | PDF 文字提取 | BSD-3-Clause |
| React、React DOM、Vite | UI 与构建工具 | MIT |
| TypeScript、Playwright Test | 类型检查与浏览器验收 | Apache-2.0 |
| pytest | Python 自动测试 | MIT |

SQLite 通过 Python 标准库 sqlite3 使用。本地 Embedding 使用标准库完成散列与归一化。完整解析版本及 npm 包完整性校验分别见 requirements.lock 和 frontend/package-lock.json。兼容模型端点由使用者自行配置，模型或服务条款由所选提供方决定。

