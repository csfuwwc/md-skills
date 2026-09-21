"""Normalize author-bound homepage responses without browser or Base side effects."""
from cover_quality import cover_candidates

METRICS = ('digg_count', 'comment_count', 'collect_count', 'share_count')


def https_image(value):
    if not isinstance(value, dict):
        return None
    return next((url for url in value.get('url_list', [])
                 if isinstance(url, str) and url.startswith('https://')), None)


def extract_profile_records(payload, expected_sec_uid, collected_at, target_ids=None):
    if not expected_sec_uid:
        raise ValueError('Expected author sec_uid is required')
    if payload.get('status_code', 0) != 0:
        raise ValueError('Profile API returned a nonzero status')
    records = {}
    for item in payload.get('aweme_list') or []:
        author = item.get('author') or {}
        aid = str(item.get('aweme_id') or '')
        if not aid or author.get('sec_uid') != expected_sec_uid:
            continue
        if target_ids is not None and aid not in target_ids:
            continue
        is_photo = item.get('aweme_type') == 68 or bool(item.get('images'))
        cover = source = None
        fallback = False
        verification = 'not_available'
        if is_photo:
            images = item.get('images') or []
            cover = https_image(images[0]) if images else None
            if cover:
                source, verification = 'images[0]', 'needs_homepage_check'
        else:
            video = item.get('video') or {}
            for field in ('cover', 'origin_cover'):
                cover = https_image(video.get(field))
                if cover:
                    source = 'video.' + field
                    fallback = field != 'cover'
                    verification = 'fallback_not_display_verified' if fallback else 'api_display_cover'
                    break
        statistics = item.get('statistics') or {}
        kind = 'note' if is_photo else 'video'
        records[aid] = {
            'id': aid, 'url': f'https://www.douyin.com/{kind}/{aid}', 'type': kind,
            'authorSecUid': expected_sec_uid, 'author': author.get('nickname'),
            'caption': item.get('desc'), 'createTime': item.get('create_time'),
            'statistics': {key: statistics.get(key) for key in METRICS},
            'cover': cover, 'coverSource': source, 'coverFallback': fallback,
            'coverVerification': verification, 'collectedAt': collected_at,
            'coverCandidates': cover_candidates(item.get('video') or {}) if not is_photo else [],
            'imageUrls': [url for image in (item.get('images') or [])
                          if (url := https_image(image))] if is_photo else [],
            'video': {k:v for k,v in (item.get('video') or {}).items() if k in ('duration','play_addr','play_addr_h264','play_addr_265','download_addr','bit_rate')} if not is_photo else {},
            'videoQualities': [{'gear':t.get('gear_name'),'width':(t.get('play_addr') or {}).get('width'),'height':(t.get('play_addr') or {}).get('height'),'bitRate':t.get('bit_rate'),'isH265':t.get('is_h265'),'size':(t.get('play_addr') or {}).get('data_size')} for t in (item.get('video') or {}).get('bit_rate',[])],
            'dataSource': 'profile_post_api',
        }
    return list(records.values())
