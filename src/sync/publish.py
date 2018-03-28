from asyncio import StreamWriter
import logging
from typing import Optional

from spotify import Spotify
from sync.structures import State, Context


logger = logging.getLogger(__name__)


async def next_safe_state(spot: Spotify, context: Context,
                          *, block: bool=True) -> Optional[State]:
    data = await spot.get_playing(block=block)
    was_locked = context.lock.locked()
    with await context.lock:
        if was_locked:
            data = await spot.get_playing()
        state = State.from_json(data)
        if not state.is_update(context.state):
            state = None
        else:
            context.set_master(True, state)
            context.state = None
    return state


def encode(state: State) -> bytes:
    return f'{state.serialize()}\n'.encode()


async def publish(writer: StreamWriter, spot: Spotify,
                  context: Context) -> None:
    if context.server:
        logger.info('Publish to newcomer')
        state = await next_safe_state(spot, context, block=False)
        if state is not None:
            writer.write(encode(state))

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
