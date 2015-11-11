# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import re

from .common import InfoExtractor
from ..compat import (
    compat_urllib_request,
    compat_urllib_parse,
    compat_urllib_parse_unquote,
    compat_urllib_parse_urlparse,
)
from ..utils import (
    ExtractorError,
    float_or_none,
)


class CeskaTelevizeIE(InfoExtractor):
    _VALID_URL = r'https?://www\.ceskatelevize\.cz/(porady|ivysilani)/(?:[^/]+/)*(?P<id>[^/#?]+)/*(?:[#?].*)?$'
    _TESTS = [{
        'url': 'http://www.ceskatelevize.cz/ivysilani/ivysilani/10441294653-hyde-park-civilizace/214411058091220',
        'info_dict': {
            'id': '61924494876951776',
            'ext': 'mp4',
            'title': 'Hyde Park Civilizace',
            'description': 'md5:fe93f6eda372d150759d11644ebbfb4a',
            'thumbnail': 're:^https?://.*\.jpg',
            'duration': 3350,
        },
        'params': {
            # m3u8 download
            'skip_download': True,
        },
    }, {
        'url': 'http://www.ceskatelevize.cz/ivysilani/10532695142-prvni-republika/bonus/14716-zpevacka-z-duparny-bobina',
        'info_dict': {
            'id': '61924494876844374',
            'ext': 'mp4',
            'title': 'První republika: Zpěvačka z Dupárny Bobina',
            'description': 'Sága mapující atmosféru první republiky od r. 1918 do r. 1945.',
            'thumbnail': 're:^https?://.*\.jpg',
            'duration': 88.4,
        },
        'params': {
            # m3u8 download
            'skip_download': True,
        },
    }, {
        # video with 18+ caution trailer
        'url': 'http://www.ceskatelevize.cz/porady/10520528904-queer/215562210900007-bogotart/',
        'info_dict': {
            'id': '215562210900007-bogotart',
            'title': 'Queer: Bogotart',
            'description': 'Alternativní průvodce současným queer světem',
        },
        'playlist': [{
            'info_dict': {
                'id': '61924494876844842',
                'ext': 'mp4',
                'title': 'Queer: Bogotart (Varování 18+)',
                'duration': 10.2,
            },
        }, {
            'info_dict': {
                'id': '61924494877068022',
                'ext': 'mp4',
                'title': 'Queer: Bogotart (Queer)',
                'thumbnail': 're:^https?://.*\.jpg',
                'duration': 1558.3,
            },
        }],
        'params': {
            # m3u8 download
            'skip_download': True,
        },
    }]

    def _real_extract(self, url):
        url = url.replace('/porady/', '/ivysilani/').replace('/video/', '')

        mobj = re.match(self._VALID_URL, url)
        playlist_id = mobj.group('id')

        webpage = self._download_webpage(url, playlist_id)

        NOT_AVAILABLE_STRING = 'This content is not available at your territory due to limited copyright.'
        if '%s</p>' % NOT_AVAILABLE_STRING in webpage:
            raise ExtractorError(NOT_AVAILABLE_STRING, expected=True)

        typ = self._html_search_regex(
            r'getPlaylistUrl\(\[\{"type":"(.+?)","id":".+?"\}\],', webpage, 'type')
        episode_id = self._html_search_regex(
            r'getPlaylistUrl\(\[\{"type":".+?","id":"(.+?)"\}\],', webpage, 'episode_id')

        data = {
            'playlist[0][type]': typ,
            'playlist[0][id]': episode_id,
            'requestUrl': compat_urllib_parse_urlparse(url).path,
            'requestSource': 'iVysilani',
        }

        req = compat_urllib_request.Request(
            'http://www.ceskatelevize.cz/ivysilani/ajax/get-client-playlist',
            data=compat_urllib_parse.urlencode(data))

        req.add_header('Content-type', 'application/x-www-form-urlencoded')
        req.add_header('x-addr', '127.0.0.1')
        req.add_header('X-Requested-With', 'XMLHttpRequest')
        req.add_header('Referer', url)

        playlistpage = self._download_json(req, playlist_id)

        playlist_url = playlistpage['url']
        if playlist_url == 'error_region':
            raise ExtractorError(NOT_AVAILABLE_STRING, expected=True)

        req = compat_urllib_request.Request(compat_urllib_parse_unquote(playlist_url))
        req.add_header('Referer', url)

        playlist_title = self._og_search_title(webpage)
        playlist_description = self._og_search_description(webpage)

        playlist = self._download_json(req, playlist_id)['playlist']
        playlist_len = len(playlist)

        entries = []
        for item in playlist:
            formats = []
            for format_id, stream_url in item['streamUrls'].items():
                formats.extend(self._extract_m3u8_formats(
                    stream_url, playlist_id, 'mp4', entry_protocol='m3u8_native'))
            self._sort_formats(formats)

            item_id = item.get('id') or item['assetId']
            title = item['title']

            duration = float_or_none(item.get('duration'))
            thumbnail = item.get('previewImageUrl')

            subtitles = {}
            if item.get('type') == 'VOD':
                subs = item.get('subtitles')
                if subs:
                    subtitles = self.extract_subtitles(episode_id, subs)

            entries.append({
                'id': item_id,
                'title': playlist_title if playlist_len == 1 else '%s (%s)' % (playlist_title, title),
                'description': playlist_description if playlist_len == 1 else None,
                'thumbnail': thumbnail,
                'duration': duration,
                'formats': formats,
                'subtitles': subtitles,
            })

        return self.playlist_result(entries, playlist_id, playlist_title, playlist_description)

    def _get_subtitles(self, episode_id, subs):
        original_subtitles = self._download_webpage(
            subs[0]['url'], episode_id, 'Downloading subtitles')
        srt_subs = self._fix_subtitles(original_subtitles)
        return {
            'cs': [{
                'ext': 'srt',
                'data': srt_subs,
            }]
        }

    @staticmethod
    def _fix_subtitles(subtitles):
        """ Convert millisecond-based subtitles to SRT """

        def _msectotimecode(msec):
            """ Helper utility to convert milliseconds to timecode """
            components = []
            for divider in [1000, 60, 60, 100]:
                components.append(msec % divider)
                msec //= divider
            return "{3:02}:{2:02}:{1:02},{0:03}".format(*components)

        def _fix_subtitle(subtitle):
            for line in subtitle.splitlines():
                m = re.match(r"^\s*([0-9]+);\s*([0-9]+)\s+([0-9]+)\s*$", line)
                if m:
                    yield m.group(1)
                    start, stop = (_msectotimecode(int(t)) for t in m.groups()[1:])
                    yield "{0} --> {1}".format(start, stop)
                else:
                    yield line

        return "\r\n".join(_fix_subtitle(subtitles))
