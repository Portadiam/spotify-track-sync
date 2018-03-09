import argparse
import sys
import webbrowser

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Protocol
else:
    Protocol = object


DEFAULT_IP = '0.0.0.0'
DEFAULT_PORT = 9898


class Arguments(Protocol):
    token: str
    ip: str
    port: int


def get() -> Arguments:
    parser = argparse.ArgumentParser()
    parser.add_argument('token', type=str, nargs='?', default='')
    parser.add_argument('ip', type=str, nargs='?', default=DEFAULT_IP)
    parser.add_argument('port', type=int, nargs='?', default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.token == '':
        webbrowser.open('https://open.spotify.com/token', autoraise=True)
        sys.exit(0)
    return args
