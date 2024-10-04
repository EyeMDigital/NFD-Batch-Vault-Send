import os
import json
import base64
import msgpack
import requests
from dotenv import load_dotenv
from algosdk import mnemonic, transaction
from algosdk.v2client import algod

# Load environment variables
load_dotenv()
SENDER_ADDRESS = os.getenv("SENDER_ADDRESS")
MNEMONIC = os.getenv("MNEMONIC")

# Constants
ALGOD_ADDRESS = "https://mainnet-api.algonode.cloud"
ALGOD_TOKEN = ""
ASSET_ID = 1183554043
TOTAL_AMOUNT = 50000  # micro-units
PARENT_APP_ID = 1728279779  # Provided parent app ID

# Initialize Algod client
algod_client = algod.AlgodClient(ALGOD_TOKEN, ALGOD_ADDRESS)
private_key = mnemonic.to_private_key(MNEMONIC)

def get_segments(parent_app_id):
    API_URL = "https://api.nf.domains/nfd/v2/search"
    headers = {"Content-Type": "application/json"}
    params = {
        "parentAppID": parent_app_id,
        "limit": 200,  # Adjust as needed, max 200 as per documentation
        "view": "brief"
    }

    response = requests.get(API_URL, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        nfds = data.get("nfds", [])
        segments = [nfd["name"] for nfd in nfds]
        return segments
    else:
        print("Error fetching segments from API:", response.text)
        exit(1)

def send_asset_to_vault(nfd_name, amount, asset_id, sender_address):
    API_URL = f"https://api.nf.domains/nfd/vault/sendTo/{nfd_name}"
    headers = {"Content-Type": "application/json"}
    request_body = {
        "sender": sender_address,
        "assets": [asset_id],
        "amount": amount,
        "note": "Distributing asset to NFD vault",
        "optInOnly": False
    }
    response = requests.post(API_URL, headers=headers, json=request_body)
    if response.status_code == 200:
        outer_json = response.json()
        txns_data = json.loads(outer_json)
        return txns_data
    else:
        print(f"Error fetching transactions for NFD {nfd_name}: {response.text}")
        return None

def submit_transactions(txns_data):
    txns = []
    signed_txns = []

    for txn_info in txns_data:
        if isinstance(txn_info, list) and len(txn_info) == 2:
            txn_type = txn_info[0]
            txn_base64 = txn_info[1]

            if txn_type == "u":
                # Unsigned transaction
                txn_bytes = base64.b64decode(txn_base64)
                txn_dict = msgpack.unpackb(txn_bytes, raw=False)
                txn = transaction.Transaction.undictify(txn_dict)
                txns.append(txn)
                signed_txns.append(None)  # Placeholder
            elif txn_type == "s":
                # Signed transaction
                signed_txn_bytes = base64.b64decode(txn_base64)
                signed_txn = transaction.SignedTransaction.undictify(
                    msgpack.unpackb(signed_txn_bytes, raw=False)
                )
                txns.append(signed_txn.transaction)
                signed_txns.append(signed_txn)
            else:
                print("Unknown transaction type:", txn_type)
                continue
        else:
            print("Invalid transaction format:", txn_info)
            continue

    # Sign the unsigned transactions
    for i, stxn in enumerate(signed_txns):
        if stxn is None:
            signed_txn = txns[i].sign(private_key)
            signed_txns[i] = signed_txn

    # Submit the transaction group
    try:
        txid = algod_client.send_transactions(signed_txns)
        print(f"Transaction submitted with ID: {txid}")
        # Wait for confirmation
        from algosdk.transaction import wait_for_confirmation
        confirmed_txn = wait_for_confirmation(algod_client, txid, 4)
        print("Transaction confirmed in round", confirmed_txn.get("confirmed-round", 0))
    except Exception as e:
        print(f"Error submitting transactions: {e}")

def calculate_distribution(total_amount, segments):
    num_segments = len(segments)
    if num_segments == 0:
        print("No segments found for the parent app ID.")
        exit(1)
    amount_per_segment = total_amount // num_segments
    remainder = total_amount % num_segments
    return amount_per_segment, remainder

def process_transactions(segments, amount_per_segment, remainder):
    for idx, nfd_name in enumerate(segments):
        amount = amount_per_segment
        if remainder > 0 and idx < remainder:
            amount += 1  # Distribute remainder

        print(f"\nProcessing NFD: {nfd_name}")
        txns_data = send_asset_to_vault(nfd_name, amount, ASSET_ID, SENDER_ADDRESS)
        if txns_data is None:
            print(f"Failed to get transactions for {nfd_name}")
            continue

        # Process and submit transactions
        submit_transactions(txns_data)

def main():
    segments = get_segments(PARENT_APP_ID)
    if not segments:
        print(f"No segments found for parent app ID {PARENT_APP_ID}")
        exit(1)

    amount_per_segment, remainder = calculate_distribution(TOTAL_AMOUNT, segments)

    print(f"Found {len(segments)} segments:")
    for s in segments:
        print(f" - {s}")

    print(f"\nTotal amount to distribute: {TOTAL_AMOUNT} micro-units")
    print(f"Amount per segment: {amount_per_segment} micro-units")
    if remainder > 0:
        print(f"Remaining amount: {remainder} micro-units will be distributed to the first {remainder} segments")

    confirm = input("Do you want to proceed with the transactions? (yes/no): ")
    if confirm.lower() != "yes":
        print("Operation cancelled.")
        exit(0)

    process_transactions(segments, amount_per_segment, remainder)

if __name__ == "__main__":
    main()
