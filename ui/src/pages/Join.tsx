import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"
import { toast } from "react-toastify"
import { useAccount, useBalance } from "wagmi"
import { estimateFeesPerGas, writeContract } from "wagmi/actions"
import { abi } from "../abi"
import TermsModal from "../components/TermsModal"
import { config } from "../config"
import { COMMISSION_PERCENTAGE, MAX_GAS, SC_ADDRESS, chainId } from "../constants"
import { socket } from "../socket"
import { GameInfo, StartData } from "../types"
import { POLtoGBP, POLtoUSD, parsePOL } from "../utils/currency"

export default function Join() {
  const navigate = useNavigate()
  const [joiningGameId, setJoiningGameId] = useState("")
  const [gameInfo, setGameInfo] = useState<GameInfo | null>(null)
  const [wagerAmountUSD, setWagerAmountUSD] = useState<number>(0)
  const [wagerAmountGBP, setWagerAmountGBP] = useState<number>(0)
  const [wagerPlusCommissionWei, setWagerPlusCommissionWei] = useState<bigint>() // in Wei
  const [gasPrice, setGasPrice] = useState<bigint>(0n)
  const [showModal, setShowModal] = useState<boolean>(false)

  const [loading, setLoading] = useState(0) // 0: off, 1: fetching game details, 2: joining game

  const { address, isConnected } = useAccount()
  const { data: balance } = useBalance({ address, chainId })

  useEffect(() => {
    function onStart(data: StartData) {
      navigate("/play", {
        state: {
          colour: data.colour,
          timeRemaining: data.timeRemaining,
          round: data.round,
          totalRounds: data.totalRounds,
          roundStartTimestamp: data.roundStartTimestamp
        },
      })
    }

    async function onGameInfo(data: GameInfo) {
      setWagerAmountUSD(await POLtoUSD(data.wagerAmount))
      setWagerAmountGBP(await POLtoGBP(data.wagerAmount))

      const wagerWei = parsePOL(data.wagerAmount.toString())
      const commissionWei = (wagerWei * BigInt(COMMISSION_PERCENTAGE)) / BigInt(100)
      setWagerPlusCommissionWei(wagerWei + commissionWei)

      setGameInfo(data)
      setLoading(0)
    }

    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    function onError(_1: string) {
      setLoading(0)
    }

    socket.on("start", onStart)
    socket.on("gameInfo", onGameInfo)
    socket.on("error", onError)

    return () => {
      socket.off("start", onStart)
      socket.off("gameInfo", onGameInfo)
      socket.off("error", onError)
    }
  }, [navigate])

  useEffect(() => {
    async function fetchGasPrice() {
      if (isConnected) {
        const priceInfo = await estimateFeesPerGas(config, {
          chainId,
        }) // gets estimated gas price in wei
        setGasPrice(priceInfo.maxFeePerGas)
      }
    }
    fetchGasPrice()
  }, [isConnected])

  function onSubmitGameId() {
    socket.emit("getGameDetails", joiningGameId)
  }

  async function validateAcceptGame() {
    if (!gameInfo) return "Something went wrong"
    if (!isConnected) return "Please connect your wallet."
    const priceInfo = await estimateFeesPerGas(config, {
      chainId,
    })
    const gasPrice = priceInfo.maxFeePerGas

    if (wagerPlusCommissionWei! >= balance!.value - gasPrice) return "Insufficient MATIC balance."
    return 0
  }

  async function onAcceptGame() {
    const err = await validateAcceptGame()
    if (err) {
      toast.error(err)
      setLoading(0)
      return
    }
    try {
      const result = await writeContract(config, {
        abi,
        address: SC_ADDRESS,
        functionName: "joinGame",
        value: wagerPlusCommissionWei,
        gas: MAX_GAS,
        args: [joiningGameId],
      })
      console.log("Transaction successful:", result)
      socket.emit("acceptGame", joiningGameId, address)
      setLoading(0)
    } catch (err) {
      console.error("Transaction error:", err)
      toast.error((err as Error).message.split(".")[0])
      setLoading(0)
    }
  }

  return (
    <>
      <div className="home-div">
        <h4>Join game</h4>
        {!gameInfo && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              setLoading(1)
              onSubmitGameId()
            }}
          >
            <input type="text" placeholder="Enter game code" value={joiningGameId} onChange={(e) => setJoiningGameId(e.currentTarget.value)} required />
            <button type="submit" className={loading == 1 ? "loading" : ""}>
              View game details{loading == 1 && <span className="spinner" />}
            </button>
          </form>
        )}
        {gameInfo && (
          <>
            <p>Game code: {joiningGameId}</p>
            <p>Time control: {gameInfo.timeControl}m</p>
            <p>Rounds: {gameInfo.totalRounds}</p>
            <p>
              Wager: {gameInfo.wagerAmount} POL ({wagerAmountUSD.toFixed(2)} USD / {wagerAmountGBP.toFixed(2)} GBP)
            </p>
            <p>Gas price: {(Number(gasPrice) / 10 ** 9).toFixed(2)} Gwei</p>
            <p>Commission: {COMMISSION_PERCENTAGE}%</p>
            <form
              onSubmit={(e) => {
                e.preventDefault()
                setLoading(2)
                onAcceptGame()
              }}
            >
              <div className="accept-terms-container">
                <input type="checkbox" id="accept-terms" required />
                <label htmlFor="accept-terms">
                  I accept the{" "}
                  <a href="#" onClick={() => setShowModal(true)}>
                    terms of use
                  </a>
                </label>
              </div>
              <button type="submit" className={loading == 2 ? "loading" : ""}>
                Join and start game{loading == 2 && <span className="spinner" />}
              </button>
            </form>
          </>
        )}
        <button onClick={() => navigate("/")} disabled={loading > 0}>
          Back
        </button>
      </div>
      <TermsModal show={showModal} setShow={setShowModal} />
    </>
  )
}
