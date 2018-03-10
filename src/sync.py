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

    def is_update(self, old: 'State') -> bool:
        return (
            self.is_distinct(old) or
            abs(self.seek - old.seek) > 5 or
            self.pause != old.pause
        )


class Context:
    _state: State = None

    def __init__(self, *, server=False) -> None:
        self._server = server

    @property
    def state(self) -> State:
        return self._state

    @state.setter
    def state(self, value: State) -> None:
        if not self._server:
            self._state = value


async def sync(token: str, reader: StreamReader, writer: StreamWriter,
               *, server: bool=False) -> None:
    connector = aiohttp.TCPConnector(resolver=aiohttp.AsyncResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        spot = Spotify(session, token)
        context = Context(server=server)
        await asyncio.wait([
            publish(writer, spot, context, server=server) if server else
            subscribe(reader, spot, context)
        ], return_when=asyncio.FIRST_COMPLETED)


async def next_safe_state(spot: Spotify, context: Context) -> Optional[State]:
    global lock

    data = await spot.get_playing(block=True)
    was_locked = lock.locked()
    with await lock:
        if was_locked:
            data = await spot.get_playing()
        state = State.from_json(data)
        if not state.is_update(context.state):
            state = None
        context.state = None
    return state


def encode(state: State) -> bytes:
    return f'{state.serialize()}\n'.encode()


async def publish(writer: StreamWriter, spot: Spotify, context: Context,
                  *, server: bool=False) -> None:
    if server:
        logger.info('Publish to newcomer')
        try:
            writer.write(encode(State.from_json(await spot.get_playing())))
        except KeyError:
            logger.info('Can\'t publish because no initial track')

    while True:
        try:
            logger.info('Publish waiting')
            state = await next_safe_state(spot, context)
            if state is not None:
                writer.write(encode(state))
        except KeyError:
            logger.warning('KeyError during loop')
            pass
        except ConnectionResetError:
            logger.warning('ConnectionResetError during loop')
            return


async def safe_update(message: State, spot: Spotify, context: Context) -> None:
    global lock

    with await lock:
        old_state = State.from_json(await spot.get_playing())
        if message.is_update(old_state):
            await spot.play(message.uri, message.seek)
            if message.pause:
                await spot.pause()
            context.state = message


async def subscribe(reader: StreamReader, spot: Spotify,
                    context: Context) -> None:
    logger.info('Subscribe ready')
    while True:
        try:
            logger.debug(f'Waiting for Get')
            raw_message = (await reader.readline()).decode().strip()
            logger.debug(f'Get raw message {raw_message}')
            message = State(**json.loads(raw_message))
            logger.info(f'Get {message}')

            await safe_update(message, spot, context)
        except ConnectionResetError:
            logger.warning('ConnectionResetError during loop')
            return
