from logging import Logger

from app.abi import abi
from app.constants import SC_ADDRESS, WALLET_PK
from eth_utils import encode_hex
from web3 import AsyncWeb3


class GameContract:
    """Wrapper around smart contract functions declareWinner and declareDraw"""

    GAS_LIMIT = 100_000

    def __init__(self, w3: AsyncWeb3, logger: Logger):
        self.w3 = w3
        self.contract = w3.eth.contract(address=SC_ADDRESS, abi=abi)
        self.acct = w3.eth.account.from_key(WALLET_PK)
        self.logger = logger

    async def declare_winner(self, gid: str, winner_addr: str):
        """Declare winner of game"""
        tx = await self.contract.functions.declareWinner(gid, winner_addr).build_transaction(
            {
                "from": self.acct.address,
                "gas": self.GAS_LIMIT,
                "nonce": await self.w3.eth.get_transaction_count(self.acct.address),
            }
        )
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.acct.key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        self.logger.info(f"Winner declared in game {gid}. Transaction hash: {encode_hex(tx_hash)}")
        return await self.w3.eth.wait_for_transaction_receipt(tx_hash)

    async def declare_draw(self, gid: str):
        """Declare draw in game"""
        tx = await self.contract.functions.declareDraw(gid).build_transaction(
            {
                "from": self.acct.address,
                "gas": self.GAS_LIMIT,
                "nonce": await self.w3.eth.get_transaction_count(self.acct.address),
            }
        )
        signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.acct.key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        self.logger.info(f"Draw declared in game {gid}. Transaction hash: {encode_hex(tx_hash)}")
        return await self.w3.eth.wait_for_transaction_receipt(tx_hash)
