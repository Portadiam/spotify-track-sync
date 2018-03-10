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


class LocalState:
    state: State = None


async def sync(token: str, reader: StreamReader, writer: StreamWriter,
               *, server: bool=False) -> None:
    connector = aiohttp.TCPConnector(resolver=aiohttp.AsyncResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        spot = Spotify(session, token)
        received_state = LocalState()
        # Detach publish and subscribe LocalState if this is the server
        # This is to allow the server to propagate updates to other clients
        received_state_publish = LocalState() if server else received_state
        await asyncio.wait([
            publish(writer, spot, received_state_publish, server=server)
            if server else
            subscribe(reader, spot, received_state)
        ], return_when=asyncio.FIRST_COMPLETED)


async def next_safe_state(spot: Spotify, received_state: LocalState
                          ) -> Optional[State]:
    global lock

    data = await spot.get_playing(block=True)
    was_locked = lock.locked()
    with await lock:
        if was_locked:
            data = await spot.get_playing()
        state = State.from_json(data)
        if not is_update(state, received_state.state):
            state = None
        received_state.state = None
    return state


def encode(state: State) -> bytes:
    return f'{state.serialize()}\n'.encode()


async def publish(writer: StreamWriter, spot: Spotify,
                  received_state: LocalState, *, server: bool=False) -> None:
    if server:
        logger.info('Publish to newcomer')
        try:
            writer.write(encode(State.from_json(await spot.get_playing())))
        except KeyError:
            logger.info('Can\'t publish because no initial track')

    while True:
        try:
            logger.info('Publish waiting')
            state = await next_safe_state(spot, received_state)
            if state is not None:
                writer.write(encode(state))
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


async def safe_update(message: State, spot: Spotify,
                      received_state: LocalState) -> None:
    global lock

    with await lock:
        old_state = State.from_json(await spot.get_playing())
        if is_update(message, old_state):
            await spot.play(message.uri, message.seek)
            if message.pause:
                await spot.pause()
            received_state.state = message


async def subscribe(reader: StreamReader, spot: Spotify,
                    received_state: LocalState) -> None:
    logger.info('Subscribe ready')
    while True:
        try:
            logger.debug(f'Waiting for Get')
            raw_message = (await reader.readline()).decode().strip()
            logger.debug(f'Get raw message {raw_message}')
            message = State(**json.loads(raw_message))
            logger.info(f'Get {message}')

            await safe_update(message, spot, received_state)
        except ConnectionResetError:
            logger.warning('ConnectionResetError during loop')
            return
