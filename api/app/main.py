import logging
from contextlib import asynccontextmanager

import aioredis
from app.constants import ALCHEMY_API_URL, CLOUDAMQP_URL, REDIS_URL
from app.exceptions import SocketIOExceptionHandler
from app.exchange import router as exchange_router
from app.stats import build_stats_router
from app.game_contract import GameContract
from app.game_controller import GameController
from app.game_registry import GameRegistry
from app.log_formatter import custom_formatter
from app.play_controller import PlayController
from app.rate_limit import TokenBucketRateLimiter
from app.rmq import RMQConnectionManager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_socketio import SocketManager
from web3 import AsyncWeb3
from web3.middleware import async_geth_poa_middleware
from urllib.parse import urlparse

# logging config (override uvicorn default)
logger = logging.getLogger("uvicorn")
logger.handlers[0].setFormatter(custom_formatter)

# web3
w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(ALCHEMY_API_URL))
w3.middleware_onion.inject(async_geth_poa_middleware, layer=0)

# game registry
gr = GameRegistry()

# connection token bucket (rate limiting)
rate_limiter = TokenBucketRateLimiter()

# Redis client and MQ setup
rurl = urlparse(REDIS_URL)
redis_client = aioredis.Redis(host=rurl.hostname, port=rurl.port, password=rurl.password, ssl=(rurl.scheme == "rediss"), ssl_cert_reqs=None)

# RabbitMQ connection manager (pika)
rmq = RMQConnectionManager(CLOUDAMQP_URL, logger)


@asynccontextmanager
async def lifespan(_):
    """Handles startup/shutdown"""
    # Start token refiller
    rate_limiter.start_refiller()

    yield

    # Clean up before shutdown
    rate_limiter.stop_refiller()
    gr.clear()  # clear game registry
    if rmq.channel is not None and rmq.channel.is_open:  # close MQ
        rmq.channel.close()
    async for key in redis_client.scan_iter("game:*"):  # clear all games from redis cache
        await redis_client.delete(key)
    await redis_client.close()  # close redis connection


chess_api = FastAPI(lifespan=lifespan)

chess_api.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://dechecs.netlify.app",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

chess_api.include_router(exchange_router)
chess_api.include_router(build_stats_router(redis_client))

socket_manager = SocketManager(app=chess_api)

# Contract wrapper
contract = GameContract(w3, logger)

# Game controller
gc = GameController(rmq, redis_client, chess_api.sio, gr, contract, logger)

# Play (in game events) controller
pc = PlayController(rmq, chess_api.sio, gc, logger)

# Global exception handler for controller methods
sioexc = SocketIOExceptionHandler(chess_api.sio, rmq, logger)

# Connect/disconnect handlers


@chess_api.sio.on("connect")
async def connect(sid, _):
    if rate_limiter.consume_token():
        logger.info(f"Client {sid} connected")
    else:
        await chess_api.sio.emit("error", "Connection limit exceeded", to=sid)
        logger.warning(f"Connection limit exceeded. Disconnecting {sid}")
        await chess_api.sio.disconnect(sid)


@chess_api.sio.on("disconnect")
async def disconnect(sid):
    await gc.handle_exit(sid)
    logger.info(f"Client {sid} disconnected")


# Game management event handlers


@chess_api.sio.on("create")
@sioexc.sio_exception_handler
async def create(sid, time_control, wager, wallet_addr, n_rounds):
    await gc.create(sid, time_control, wager, wallet_addr, n_rounds)


@chess_api.sio.on("cancel")
@sioexc.sio_exception_handler
async def cancel_game(sid, created_on_contract):
    """Game creator cancels the game and cashes out"""
    await gc.cancel_game(sid, created_on_contract)


@chess_api.sio.on("getGameDetails")
@sioexc.sio_exception_handler
async def get_game_details(sid, gid):
    await gc.get_game_details(sid, gid)


@chess_api.sio.on("acceptGame")
@sioexc.sio_exception_handler
async def accept_game(sid, gid, wallet_addr):
    await gc.accept_game(sid, gid, wallet_addr)


# In-game event handlers


@chess_api.sio.on("move")
@sioexc.sio_exception_handler
async def move(sid, uci):
    await pc.move(sid, uci)


@chess_api.sio.on("offerDraw")
@sioexc.sio_exception_handler
async def offer_draw(sid):
    await pc.offer_draw(sid)


@chess_api.sio.on("acceptDraw")
@sioexc.sio_exception_handler
async def accept_draw(sid):
    await pc.accept_draw(sid)


@chess_api.sio.on("resign")
@sioexc.sio_exception_handler
async def resign(sid):
    await pc.resign(sid)


# NOTE: flag means run out of clock time


@chess_api.sio.on("flag")
@sioexc.sio_exception_handler
async def flag(sid, flagged):
    await pc.flag(sid, flagged)


# Rematch (game management)


@chess_api.sio.on("offerRematch")
@sioexc.sio_exception_handler
async def offer_rematch(sid):
    await gc.offer_rematch(sid)


@chess_api.sio.on("acceptRematch")
@sioexc.sio_exception_handler
async def accept_rematch(sid):
    await gc.accept_rematch(sid)


# Exit game handler


@chess_api.sio.on("exit")
@sioexc.sio_exception_handler
async def exit(sid):
    """When a client exits the game/match, clear it from game registry and cache"""
    await gc.handle_exit(sid)
