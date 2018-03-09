import asyncio
from asyncio import StreamReader, StreamWriter, Lock
import aiohttp
import logging
from typing import Dict, Any, Callable, Awaitable, NamedTuple, Optional
import json

from spotify import Spotify


JsonObject = Dict[str, Any]
ChangeFunc = Callable[[Spotify], Awaitable]

lock = Lock()

logger = logging.getLogger(__name__)


async def sync(token: str, reader: StreamReader, writer: StreamWriter,
               *, server: bool=False) -> None:
    connector = aiohttp.TCPConnector(resolver=aiohttp.AsyncResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        spot = Spotify(session, token)
        await asyncio.wait([
            publish(writer, spot, server=server),
            subscribe(reader, spot)
        ], return_when=asyncio.FIRST_COMPLETED)


def uri(data: JsonObject) -> str:
    return data['track']['track_resource']['uri']


def playing(data: JsonObject) -> bool:
    return data['playing']


def position(data: JsonObject) -> int:
    return int(data['playing_position'])


async def next_safe_state(spot: Spotify) -> JsonObject:
    global lock

    state = await spot.get_playing(block=True)
    if lock.locked():
        with await lock:
            state = await spot.get_playing()
    return state


def serialize(state: JsonObject) -> str:
    message = {
        'uri': uri(state),
        'seek': position(state),
        'pause': not playing(state)
    }
    return json.dumps(message)


def encode(state: JsonObject) -> bytes:
    return f'{serialize(state)}\n'.encode()


async def publish(writer: StreamWriter, spot: Spotify, *, server: bool=False
                  ) -> None:
    if server:
        logger.info('Publish to newcomer')
        try:
            writer.write(encode(await spot.get_playing()))
        except KeyError:
            logger.info('Can\'t publish because no initial track')

    while True:
        try:
            logger.info('Publish waiting')
            writer.write(encode(await next_safe_state(spot)))
        except KeyError:
            logger.warning('KeyError during loop')
            pass
        except ConnectionResetError:
            logger.warning('ConnectionResetError during loop')
            return


class Message(NamedTuple):
    uri: str
    seek: int
    pause: bool

    @staticmethod
    def from_json(state: JsonObject) -> Optional['Message']:
        try:
            return Message(
                uri=state['uri'], seek=state['seek'], pause=state['pause']
            )
        except KeyError:
            return None


def is_update(new: Message, old: Message) -> bool:
    return (
        old is None or
        new.uri != old.uri or
        abs(new.seek - old.seek) > 5 or
        new.pause != old.pause
    )


async def safe_update(message: Message, spot: Spotify) -> None:
    global lock

    with await lock:
        old_state = Message.from_json(await spot.get_playing())
        if is_update(message, old_state):
            await spot.play(message.uri, message.seek)
            if message.pause:
                await spot.pause()


async def subscribe(reader: StreamReader, spot: Spotify) -> None:
    logger.info('Subscribe ready')
    while True:
        try:
            logger.debug(f'Waiting for Get')
            raw_message = (await reader.readline()).decode().strip()
            logger.debug(f'Get raw message {raw_message}')
            message = Message(**json.loads(raw_message))
            logger.info(f'Get {message}')

            await safe_update(message, spot)
        except ConnectionResetError:
            logger.warning('ConnectionResetError during loop')
            return
