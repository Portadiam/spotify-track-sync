import json
import logging
from asyncio import Lock
from typing import Dict, Any, NamedTuple, Optional


JsonObject = Dict[str, Any]

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

    def is_distinct(self, old: 'State') -> bool:
        return old is None or self.uri != old.uri

    def is_update(self, old: 'State') -> bool:
        return (
            self.is_distinct(old) or
            abs(self.seek - old.seek) > 5 or
            self.pause != old.pause
        )


class Context:
    _next_id: int = 0
    _state: State = None

    lock: Lock
    server: bool

    def __init__(self, lock: Lock, *, server=False) -> None:
        self.id = Context._next_id
        Context._next_id += 1
        self.lock = lock
        self.server = server
        self._master = server

    @property
    def state(self) -> State:
        return self._state

    @state.setter
    def state(self, value: State) -> None:
        if not self.server:
            self._state = value

    @property
    def master(self) -> bool:
        return self._master

    @master.setter
    def master(self, master: bool) -> None:
        if self._master != master:
            logger.info(f'Context {self.id} master {master}')
            self._master = master

    def set_master(self, master, new_state: State) -> None:
        if new_state.is_distinct(self.state):
            self.master = master
