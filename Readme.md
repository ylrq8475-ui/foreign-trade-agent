# AI 外贸客户自动开发系统

## 项目简介

这是一个面向外贸业务员和小团队的 `MVP` 工具，用来帮助我们完成下面这条最小闭环：

`找客户 -> 看官网 -> 生成客户画像 -> 生成开发信草稿 -> 人工审核 -> 记录发送状态`

当前系统重点服务于：

- 需要做小规模、精准开发的外贸业务员
- 有明确产品线和目标国家的 B2B 场景
- 需要 `AI 辅助`，但仍然坚持 `人工审核发送` 的团队

当前项目已经接入：

- `Google Places API`：用于寻找海外客户线索
- `MiniMax API`：用于客户画像和邮件草稿生成

## 当前第一版范围

第一版优先做这些：

- 用关键词 + 国家搜索客户
- 保存客户基础信息
- 抓取官网公开文本
- 生成客户画像
- 生成开发信草稿
- 在后台查看客户详情
- 人工修改、审核、标记发送

第一版暂时不追求：

- 大规模群发
- 自动回信闭环
- 复杂 CRM 权限体系
- 多人团队协作
- 完整统计报表

## 当前实现状态

已完成：

- Google Places 真实搜索
- MiniMax 真实调用
- 客户列表页
- 客户详情页
- 官网抓取与基础解析
- 客户画像生成
- 开发信草稿生成
- 草稿人工编辑
- 草稿审核通过
- 标记已发送
- 本地 JSON 持久化

进行中：

- 官网正文抽取质量优化
- 邮件草稿自然度优化
- 客户筛选精度优化

未完成：

- 正式 SMTP 发信闭环
- IMAP / Gmail / Outlook 回信接收
- 自动跟进提醒
- 完整数据库迁移

## 项目结构

```text
project/
├── ai/
├── config/
├── crawler/
├── data/
├── database/
├── mail/
├── maps/
├── scripts/
├── web/
├── main.py
├── requirements.txt
└── Readme.md
```

## 启动方式

推荐直接运行：

```bash
python main.py
```

说明：

- 如果环境里已安装 `FastAPI/uvicorn`，会启动 FastAPI 后台
- 如果没有这些依赖，会自动回退到标准库简易后台

显式启动 FastAPI：

```bash
uvicorn web.app:app --reload
```

## 环境变量

在项目根目录创建 `.env`：

```env
GOOGLE_MAPS_API_KEY=your_google_maps_api_key
GOOGLE_MAPS_USE_ENV_PROXY=true
GOOGLE_MAPS_PROXY_URL=

MINIMAX_API_KEY=your_minimax_api_key
MINIMAX_BASE_URL=https://api.minimaxi.com/v1
MINIMAX_MODEL=MiniMax-M2.7

YOUR_COMPANY_NAME=Your Company
YOUR_COMPANY_TYPE=manufacturer
YOUR_PRODUCTS=food-grade silicone kitchen tools
YOUR_ADVANTAGE=stable quality, flexible MOQ, and reliable lead times
```

## Google Places 说明

Google Places 主要用于：

- 找客户
- 获得地点标识 `place_id`
- 辅助判断客户类型

系统长期保存的核心业务数据应以这些为主：

- `place_id`
- 官网公开信息
- 人工备注
- 邮件草稿
- 跟进记录

## 邮件生成原则

当前邮件写法坚持这几个原则：

- 必须结合客户官网真实信息
- 不堆砌“我们是工厂”的表达
- 优先让客户感受到：
  - 稳定
  - 沟通顺
  - 质量稳
  - 交期靠谱
- 只挑最相关的 1-2 条工厂优势
- 结尾只问一个轻问题

## 我方工厂背景

系统当前默认使用的我方工厂背景是：

- 20+ 年制造经验
- 专注 `silicone + plastic` 厨房用品
- 主要产品：
  - silicone spatulas
  - silicone scrapers
  - silicone brushes
  - baking tools
  - collapsible silicone products
  - selected plastic kitchenware
- 支持：
  - OEM / ODM
  - Pantone 配色
  - logo printing
  - food-grade production
  - FDA / LFGB
  - TUV / SGS testing support

## 已内置的邮件 skill

系统外还额外创建了一个全局 skill：

`factory-customer-email-match`

作用是：

- 把客户网站特征和我方工厂优势匹配起来
- 生成更贴近实际业务的英文开发信
- 避免模板腔和工厂炫耀式写法

## 部署与算力建议

当前第一版算力要求不高：

- `2 核 CPU`
- `4GB-8GB 内存`
- `无需 GPU`

真正的瓶颈更可能是：

- Google Places API 成本
- MiniMax API 成本
- 网络稳定性
- 官网抓取质量

## 当前主要风险

- 不是所有官网都能稳定提取到干净正文
- Google Places 搜索结果仍可能混入零售店或不合适客户
- 邮件草稿仍需人工审核
- 当前持久化方案是 JSON，不适合长期正式运营

## 下一步优先级

建议优先继续做：

1. 提升官网正文抽取质量
2. 提升邮件草稿自然度
3. 把 JSON 仓储切换到正式数据库
4. 增加回信接收和跟进能力

## 合规边界

本项目不支持：

- 暴力爬取
- 绕过验证码
- 破解登录权限
- 非公开数据抓取
- 自动大规模群发
- 垃圾邮件轰炸

推荐做法：

- 使用官方 API
- 只分析公开网页
- 小规模精准开发
- 邮件人工审核后再发送

