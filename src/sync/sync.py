import asyncio
from asyncio import StreamReader, StreamWriter, Lock
import aiohttp
import logging

from spotify import Spotify
from sync.structures import Context
from sync.publish import publish
from sync.subscribe import subscribe


logger = logging.getLogger(__name__)


async def sync(token: str, reader: StreamReader, writer: StreamWriter,
               lock: Lock, *, server: bool=False) -> None:
    connector = aiohttp.TCPConnector(resolver=aiohttp.AsyncResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        spot = Spotify(session, token)
        context = Context(lock, server=server)
        await asyncio.wait([
            publish(writer, spot, context) if server else
            subscribe(reader, spot, context)
        ], return_when=asyncio.FIRST_COMPLETED)
