import asyncio
import logging

import args
from args import Arguments
import sync


async def connect(token: str, ip: str, port: int) -> None:
    reader, writer = await asyncio.open_connection(ip, port)
    await sync.sync(token, reader, writer)


def main(args: Arguments) -> None:
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect(args.token, args.ip, args.port))
    loop.close()


if __name__ == '__main__':
    args.DEFAULT_IP = '127.0.0.1'
    main(args.get())
