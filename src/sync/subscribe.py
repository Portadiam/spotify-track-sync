from asyncio import StreamReader
import logging
import json

from spotify import Spotify
from sync.structures import State, Context


logger = logging.getLogger(__name__)


async def safe_update(message: State, spot: Spotify, context: Context) -> None:
    with await context.lock:
        old_state = State.from_json(await spot.get_playing())
        if message.is_update(old_state):
            context.set_master(False, message)
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
