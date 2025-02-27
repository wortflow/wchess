from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

from chess import Board


class Colour(Enum):
    BLACK = (0, "black")
    WHITE = (1, "white")


class Castles(Enum):
    KINGSIDE = "K"
    QUEENSIDE = "Q"


class Outcome(Enum):
    TIMEOUT = 11
    RESIGNATION = 12
    AGREEMENT = 13
    ABANDONED = 14


@dataclass
class Game:
    players: List[str]  # [0] black, [1] white
    board: Board | str  # pychess board object or string when serialised
    time_control: int  # time control (minutes)
    wager: float  # wager amount
    player_wallet_addrs: Dict[str, str]  # maps sids to wallet addresses
    match_score: Dict[str, float]  # keeps track of how many rounds each player has won
    round: int  # current round
    n_rounds: int  # number of rounds
    tr_white: int  # time remaining in round (white)
    tr_black: int  # time reamining in round (black)
    finished: bool = False  # whether the game has finished
    last_turn_timestamp: int = 0  # timestamp for end of last turn (or start of round)


@dataclass
class MoveData:
    # NOTE: we break naming conventions here to avoid using hindering var name conversion
    turn: int
    winner: int
    outcome: int
    matchScore: Optional[Tuple[float, float]]  # TODO: move winner, outcome, matchScore to separate event
    move: str
    castles: Optional[str]
    isCheck: bool
    enPassant: bool
    legalMoves: List[str]
    moveStack: List[str]


@dataclass
class TimerData:
    white: int
    black: int


@dataclass
class Event:
    name: str
    data: int | str | dict
