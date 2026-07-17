# Private WeChat gateway API

Base URL: `http://api-ai.modianinc.com:8080/wechat`

Authenticate every route below with `X-API-Key: <WECHAT_API_KEY>`.

## Public article

`GET /api/public/v1/download`

Query parameters:

- `url`: full `https://mp.weixin.qq.com/s/...` article URL
- `format`: `json`, `html`, `markdown`, or `text`

The JSON response includes fields such as `title`, `nick_name`, `author`, `desc`, `content_noencode`, `create_time`, and `link`.

## Login

- `POST /api/web/login/session/:sid`: create a login session; response contains `uuid`.
- `GET /api/web/login/getqrcode`: return a QR image; send `Cookie: uuid=<uuid>`.
- `GET /api/web/login/scan`: poll login state with the same UUID cookie.
- `POST /api/web/login/bizlogin`: finalize confirmed login. Capture `auth-key` from `Set-Cookie`.

Observed scan statuses:

- `0`: waiting for scan
- `1`: confirmed; call `bizlogin`
- `2` or `3`: QR expired; create a new session
- `4` or `6`: scanned and waiting for user confirmation
- `5`: account has no bound email and cannot log in this way

## Account and history

`GET /api/web/mp/searchbiz`

- Query: `keyword`, `size`
- Cookie: `auth-key=<value>`
- Select an exact `nickname` match and retain its `fakeid`.

`GET /api/web/mp/appmsgpublish`

- Query: `id=<fakeid>`, `begin`, `size`, `keyword`
- Cookie: `auth-key=<value>`
- `publish_page` is a JSON-encoded string.
- Each `publish_list[].publish_info` is another JSON-encoded string.
- Article records are in `publish_info.appmsgex`; relevant fields include `title`, `link`, `digest`, `author_name`, `create_time`, and `is_deleted`.

## Gateway boundaries

The gateway intentionally exposes only the whitelisted routes above. The WeChat container has no public host port. Do not bypass the gateway or expose port 3000.
