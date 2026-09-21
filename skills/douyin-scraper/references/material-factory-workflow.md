# 列表媒体与下游工作流

## 能力边界

本仓库提供主页数据提取和视频下载。OSS上传由oss-upload负责；业务表字段、产品目录、分析模型、任务队列和本地归档路径由调用方实现。本文是接口约定，不代表本仓库内置了素材工厂或分析服务。

## 主页发现与初抓

复用MD-Browser返回的既有环境，按作者和作品ID验证列表响应。调用方按作品ID去重，区分新增检测与指定ID历史补采；未扫描到不等于作品删除。

输出保留完整caption、发布时间、互动数据、封面和有序imageUrls。视频新增：

- video：duration、play_addr、play_addr_h264、play_addr_265、download_addr、bit_rate中实际返回的值，用于下载。
- videoQualities：各bit_rate候选的gear、width、height、bitRate、isH265、size，供界面展示与后续选择。
- 原collectedAt和dataSource继续标明来源。临时签名URL可能过期，不打印或提交采集数据。

## 列表优先下载

调用video-download/scripts/download.py，传入原作品URL，并设置：

- VIDEO_DOWNLOAD_DOUYIN_CDP_ENDPOINT：MD-Browser返回的现有CDP端点，不替换环境。
- VIDEO_DOWNLOAD_DOUYIN_AUTHOR_ID：预期作者sec_uid。
- VIDEO_DOWNLOAD_DOUYIN_LIST_RECORD：单条主页记录JSON的本地路径。

下载器先验证列表记录来源、作品和作者。默认以短边720为目标；同分辨率优先H.264，再选较高码率。缺720时选择最近的较低分辨率；没有较低候选时选最近的较高候选。元数据记录实际选择和全部候选摘要，不把不同CDN地址计作不同清晰度，不将降级候选标成720p。

列表地址失效或下载校验失败时，经既有CDP详情页补取，不启动新的无头身份。没有列表参数时直接执行详情下载。发现平台验证/告警则停止，不切换其他路径继续。

校验作者、作品ID、视频轨和时长，成功后输出视频及.meta.json。selected_quality和video_candidates可持久保存；媒体临时URL不写入这些摘要。

## 详情更新与下游处理

详情下载的meta提供detail_updates，包含实际返回的文案、发布时间、互动数据、封面和观察时间。调用方可用明确新值覆盖当前字段，0是有效值；缺失字段不当成0或清空。是否保留首次快照由业务契约决定。列表下载没有详情check，不生成detail_updates。

建议调用方将下载、上传、分析、产品匹配和回填状态分开，失败时只重试缺失步骤。产品未匹配不应阻断授权的素材下载，可先进入待匹配目录。分析模型和帧数属于下游策略，不能由本skill声称已执行或保证完整覆盖。

平台告警只停止平台访问；已归档素材是否继续本地分析由调用方控制。运行中的批次固定代码版本，更新后不隐式重跑历史数据。
