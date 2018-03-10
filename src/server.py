import asyncio
from asyncio import StreamReader, StreamWriter, Lock
import logging

import args
from args import Arguments
import sync


LOG_FORMAT = '[%(relativeCreated)6d %(levelname)10s \
%(filename)10s:%(lineno)4s %(funcName)15s() ] %(message)s'


def main(args: Arguments) -> None:
    logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

    lock = Lock()

    async def serve(reader: StreamReader, writer: StreamWriter) -> None:
        await sync.sync(args.token, reader, writer, lock, server=True)

    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(serve, args.ip, args.port, loop=loop)
    server = loop.run_until_complete(coro)

    logging.info('Serving on {}'.format(server.sockets[0].getsockname()))
    loop.run_forever()


if __name__ == '__main__':
    main(args.get())
