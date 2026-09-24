"""Normalize author-bound TikTok homepage responses without external side effects."""

def first_https(value):
    if isinstance(value, str) and value.startswith('https://'):
        return value
    if isinstance(value, dict):
        for key in ('urlList', 'url_list'):
            for url in value.get(key) or []:
                if isinstance(url, str) and url.startswith('https://'):
                    return url
    return None


def image_urls(item):
    rows = ((item.get('imagePost') or {}).get('images') or [])
    result = []
    for image in rows:
        url = first_https(image.get('imageURL') or image.get('displayImage') or image)
        if url:
            result.append(url)
    return result


def extract_profile_records(payload, expected_handle, collected_at, target_ids=None):
    if not expected_handle:
        raise ValueError('Expected TikTok handle is required')
    status = payload.get('statusCode', payload.get('status_code', 0))
    if status not in (0, None):
        raise ValueError('TikTok profile API returned a nonzero status')
    expected = expected_handle.lstrip('@').casefold()
    records = {}
    for item in payload.get('itemList') or payload.get('item_list') or []:
        aid = str(item.get('id') or '')
        author = item.get('author') or {}
        handle = str(author.get('uniqueId') or author.get('unique_id') or '').lstrip('@')
        create_time = item.get('createTime', item.get('create_time'))
        if not aid or not aid.isdigit() or handle.casefold() != expected:
            continue
        if target_ids is not None and aid not in target_ids:
            continue
        images = image_urls(item)
        video = item.get('video') or {}
        kind = 'note' if images else 'video'
        cover = first_https(video.get('cover') or video.get('originCover'))
        if not cover and images:
            cover = images[0]
        stats = item.get('stats') or item.get('statistics') or {}
        records[aid] = {
            'id': aid,
            'url': f'https://www.tiktok.com/@{handle}/{"photo" if kind == "note" else "video"}/{aid}',
            'type': kind,
            'authorId': str(author.get('id') or author.get('uid') or ''),
            'authorHandle': handle,
            'author': author.get('nickname'),
            'caption': item.get('desc') or '',
            'createTime': create_time,
            'isPinned': bool(item.get('isPinnedItem') or item.get('is_pinned_item')),
            'statistics': {
                'play_count': stats.get('playCount', stats.get('play_count')),
                'digg_count': stats.get('diggCount', stats.get('digg_count')),
                'comment_count': stats.get('commentCount', stats.get('comment_count')),
                'collect_count': stats.get('collectCount', stats.get('collect_count')),
                'share_count': stats.get('shareCount', stats.get('share_count')),
            },
            'cover': cover,
            'imageUrls': images,
            'video': {key: video.get(key) for key in
                      ('duration', 'width', 'height', 'playAddr', 'downloadAddr', 'cover', 'originCover')
                      if video.get(key) is not None} if kind == 'video' else {},
            'collectedAt': collected_at,
            'dataSource': 'profile_item_list_api',
        }
    return list(records.values())


def account_snapshot(scope, expected_handle, observed_at):
    node = (scope or {}).get('webapp.user-detail') or (scope or {}).get('webapp_user_detail') or {}
    info = node.get('userInfo') or node.get('user_info') or {}
    user, stats = info.get('user') or {}, info.get('stats') or {}
    handle = str(user.get('uniqueId') or user.get('unique_id') or '').lstrip('@')
    if handle.casefold() != expected_handle.lstrip('@').casefold():
        raise ValueError('TikTok account data does not match target handle')
    values = {
        'platform_account_id': str(user.get('id') or ''),
        'account_name': user.get('nickname') or handle,
        'follower_count': stats.get('followerCount'),
        'following_count': stats.get('followingCount'),
        'total_favorited': stats.get('heartCount'),
        'aweme_count': stats.get('videoCount'),
        'last_crawled_at': observed_at,
    }
    if not values['platform_account_id'] or not all(type(values[k]) is int and values[k] >= 0 for k in
                                                     ('follower_count', 'following_count', 'total_favorited', 'aweme_count')):
        raise ValueError('TikTok account metrics are incomplete')
    return values
