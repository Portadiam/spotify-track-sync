from aiohttp import ClientSession
from typing import Dict, Any
import logging
from pprint import pformat


JsonObject = Dict[str, Any]


class Spotify:
    BASE_URL = 'http://local.spotilocal.com:4381/'

    def __init__(self, session: ClientSession, token: str) -> None:
        self.session = session
        self.token = token

    async def _csrf_token(self) -> str:
        request = self.session.get(f'{self.BASE_URL}simplecsrf/token.json', headers={'Origin': 'https://open.spotify.com'})
        async with request as response:
            json = await response.json()
            return json['token']

    async def _request(self, path: str, args: Dict[str, str]) -> JsonObject:
        logging.debug(f'Making request to spotify on {path}')
        logging.debug(pformat(args))
        args.update({
            'csrf': await self._csrf_token(),
            'oauth': self.token
        })
        url = f'{self.BASE_URL}{path}'
        request = self.session.get(url, params=args, headers={'Origin': 'https://open.spotify.com'}, timeout=None)
        async with request as response:
            assert response.status == 200
            return await response.json()

    def _timestr(self, secs: int) -> str:
        minutes = secs // 60
        seconds = secs % 60
        return f'{minutes:02d}:{seconds:02d}'

    async def get_playing(self, block: bool=False) -> JsonObject:
        logging.debug(f'Getting playing track with blocking {block}')
        args = {
            'returnon': '%2C'.join(['play', 'pause', 'error', 'ap']),
            'returnafter': '0' if block else '1'
        }
        result = await self._request('remote/status.json', args)
        logging.debug(f'Got track response')
        return result

    async def play(self, uri: str, time: int=0, pause=False) -> JsonObject:
        args = {
            'pause': 'false',
            'uri': uri if not time else f'{uri}%23{self._timestr(time)}'
        }
        return await self._request('remote/play.json', args)

    async def pause(self) -> JsonObject:
        return await self._request('remote/pause.json', {'pause': 'true'})
