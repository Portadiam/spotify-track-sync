import asyncio
from asyncio import Lock
import logging

import args
from args import Arguments
import sync


LOG_FORMAT = '[%(relativeCreated)6d %(levelname)10s \
%(filename)10s:%(lineno)4s %(funcName)15s() ] %(message)s'


async def connect(token: str, ip: str, port: int, lock: Lock) -> None:
    reader, writer = await asyncio.open_connection(ip, port)
    await sync.sync(token, reader, writer, lock)


def main(args: Arguments) -> None:
    logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

    loop = asyncio.get_event_loop()
    lock = Lock()
    loop.run_until_complete(connect(args.token, args.ip, args.port, lock))
    loop.close()


if __name__ == '__main__':
    args.DEFAULT_IP = '127.0.0.1'
    main(args.get())
