# Lark Base Schema

Default candidate table fields:

- `UP姓名列表`: text, required for create.
- `命中关键词`: multi-select, required for create; append new keywords for existing UPs.
- `UP主链接`: URL/text, required for dedupe and create.
- `来源视频链接`: URL/text, optional.
- `来源视频标题`: text, optional; skipped automatically if the target table does not have it.
- `粉丝数`: text, optional.
- `获赞数`: text, optional.
- `播放数`: text, optional.
- `代表作1标题`: text, optional.
- `代表作1链接`: URL/text, optional.
- `代表作2标题`: text, optional.
- `代表作2链接`: URL/text, optional.
- `代表作3标题`: text, optional.
- `代表作3链接`: URL/text, optional.
- `提供联系方式`: text, optional. Format multiple contacts as `类型: 内容 | 类型: 内容`.
- `抓取时间`: datetime/text, optional.

Core fields required for writes:

- `UP姓名列表`
- `命中关键词`
- `UP主链接`

The scripts filter optional writes by live table fields, so missing optional fields should not block collection.
