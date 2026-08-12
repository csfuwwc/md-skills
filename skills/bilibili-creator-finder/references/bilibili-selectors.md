# Bilibili Selectors And Rules

Search collection:

- Video cards: `.bili-video-card`, `.video-list .video-item`, `[class*="video-card"]`
- Video links: `a[href*="/video/"]`
- UP homepage links: `a[href*="space.bilibili.com"]`
- Next page: element with exact text `下一页`

Profile enrichment:

- Page text is used for `粉丝数`, `获赞数`, and `播放数` because Bilibili class names drift.
- Representative videos are collected from video cards with `/video/` links on the UP homepage.
- Contact detection covers email, `微信/VX/v信/商务微信`, and QQ patterns.

Captcha stop condition:

Only stop for modal/overlay captcha patterns such as `按顺序点击`, `依次点击`, `点击文字`, `请按顺序`, `验证码`, `人机验证`, or geetest/captcha classes/ids. Normal page text containing `验证` should not be treated as captcha unless it appears in an overlay.
