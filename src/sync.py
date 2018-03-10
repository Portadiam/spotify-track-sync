import asyncio
from asyncio import StreamReader, StreamWriter, Lock
import aiohttp
import logging
from typing import Dict, Any, NamedTuple, Optional
import json

from spotify import Spotify


JsonObject = Dict[str, Any]

lock = Lock()

logger = logging.getLogger(__name__)


class State(NamedTuple):
    uri: str
    seek: int
    pause: bool

    @staticmethod
    def from_json(state: JsonObject) -> Optional['State']:
        try:
            return State(
                uri=state['track']['track_resource']['uri'],
                seek=int(state['position']),
                pause=not state['playing']
            )
        except KeyError:
            return None

    def json(self) -> JsonObject:
        return self._asdict()

    def serialize(self) -> str:
        return json.dumps(self.json())


async def sync(token: str, reader: StreamReader, writer: StreamWriter,
               *, server: bool=False) -> None:
    connector = aiohttp.TCPConnector(resolver=aiohttp.AsyncResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        spot = Spotify(session, token)
        await asyncio.wait([
            publish(writer, spot, server=server) if server else
            subscribe(reader, spot)
        ], return_when=asyncio.FIRST_COMPLETED)


async def next_safe_state(spot: Spotify) -> State:
    global lock

    data = await spot.get_playing(block=True)
    if lock.locked():
        with await lock:
            data = await spot.get_playing()
    return State.from_json(data)


def encode(state: State) -> bytes:
    return f'{state.serialize()}\n'.encode()


async def publish(writer: StreamWriter, spot: Spotify, *, server: bool=False
                  ) -> None:
    if server:
        logger.info('Publish to newcomer')
        try:
            writer.write(encode(State.from_json(await spot.get_playing())))
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


def is_update(new: State, old: State) -> bool:
    return (
        old is None or
        new.uri != old.uri or
        abs(new.seek - old.seek) > 5 or
        new.pause != old.pause
    )


async def safe_update(message: State, spot: Spotify) -> None:
    global lock

    with await lock:
        old_state = State.from_json(await spot.get_playing())
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
            message = State(**json.loads(raw_message))
            logger.info(f'Get {message}')

            await safe_update(message, spot)
        except ConnectionResetError:
            logger.warning('ConnectionResetError during loop')
            return
