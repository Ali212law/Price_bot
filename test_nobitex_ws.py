import asyncio
import websockets
import json

async def test_ws():
    uri = "wss://ws.nobitex.ir/connection/websocket"
    
    try:
        print(f"Connecting to {uri}...")
        async with websockets.connect(uri) as ws:
            print("Connected!")
            
            await ws.send('{"connect": {}, "id": 1}')
            response = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"Connect response: {response[:300]}")
            
            subscribe_msg = {
                "subscribe": {
                    "channel": "public:orderbook-BTCIRT"
                },
                "id": 2
            }
            await ws.send(json.dumps(subscribe_msg))
            print("Subscribed to orderbook")
            
            for i in range(3):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=10)
                    print(f"Message {i+1}: {msg[:300]}")
                except asyncio.TimeoutError:
                    print(f"Timeout on message {i+1}")
                    break
                    
    except Exception as e:
        print(f"WS ERROR: {type(e).__name__} - {e}")

asyncio.run(test_ws())
