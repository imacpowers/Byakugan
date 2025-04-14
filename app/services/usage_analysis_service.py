import json
import time
from collections import defaultdict
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.exceptions import TransactionNotFound
from pathlib import Path

# Logic derived from usage_analyzer.py

class PYUSDUsageAnalyzer:
    """
    Analyzes PYUSD transaction patterns to infer usage, focusing on web3 activities,
    using data from a configured RPC endpoint.
    """

    def __init__(self, entity_data_file, rpc_url, pyusd_contract_address):
        """
        Initializes the analyzer with the path to the entity data file, RPC URL,
        and the PYUSD contract address.

        Args:
            entity_data_file (str): Path to a JSON file containing the address mapping.
            rpc_url (str): URL of the RPC endpoint (e.g., GCP RPC).
            pyusd_contract_address (str): The checksummed address of the PYUSD contract.
        """
        self.address_to_entity = {}  # Mapping of addresses to known entities
        self.load_entity_data(entity_data_file)
        self.w3 = Web3(HTTPProvider(rpc_url))
        self.pyusd_contract_address = self.w3.to_checksum_address(pyusd_contract_address)

        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {rpc_url}")

    def load_entity_data(self, entity_data_file):
        """
        Loads a mapping of Ethereum addresses to known entities.

        Args:
            entity_data_file (str): Path to a JSON file containing the address mapping.
        """
        try:
            with open(entity_data_file, "r") as f:
                # Convert keys to lowercase for consistent matching
                loaded_data = json.load(f)
                self.address_to_entity = {addr.lower(): entity for addr, entity in loaded_data.items()}
                print(f"Loaded {len(self.address_to_entity)} entities from {entity_data_file}")
        except FileNotFoundError:
            print(f"Warning: Entity data file not found at {entity_data_file}. Proceeding without entity mapping.")
            self.address_to_entity = {}
        except json.JSONDecodeError as e:
            print(f"Warning: Could not decode JSON from entity data file {entity_data_file}: {e}. Proceeding without entity mapping.")
            self.address_to_entity = {}
        except Exception as e:
            print(f"Warning: An unexpected error occurred loading entity data: {e}")
            self.address_to_entity = {}



    def fetch_transactions_from_rpc_2(self, start_block, end_block):
        """
        Fetches PYUSD transactions from the RPC within a specified block range.
        Uses eth_getLogs for efficiency, filtering for Transfer events.

        Args:
            start_block (int): The starting block number.
            end_block (int): The ending block number.

        Returns:
            list: A list of transaction event dictionaries, or an empty list on error/no events.
        """
        print(f"Fetching PYUSD Transfer events from block {start_block} to {end_block}")
        # Standard ERC20 Transfer event signature
        transfer_event_signature = self.w3.keccak(text="Transfer(address,address,uint256)").hex()

        try:
            # Use eth_getLogs for efficient event filtering
            logs = self.w3.eth.get_logs({
                'fromBlock': start_block,
                'toBlock': end_block,
                'address': self.pyusd_contract_address,
                'topics': [transfer_event_signature] # Filter by Transfer event signature
            })

            transactions = []
            for log in logs:
                # Decode topics and data (basic decoding for Transfer event)
                # Topic[0] is the event signature
                # Topic[1] is the indexed 'from' address (bytes32)
                # Topic[2] is the indexed 'to' address (bytes32)
                # Data contains the non-indexed 'value' (uint256)

                # Extract addresses from topics (last 20 bytes)
                from_address = '0x' + log['topics'][1].hex()[-40:]
                to_address = '0x' + log['topics'][2].hex()[-40:]
                # Decode value from data field
                value = self.w3.to_int(hexstr=log['data'].hex())

                # Fetch block timestamp (might require extra RPC call per block, consider optimizing if slow)
                block_timestamp = self.w3.eth.get_block(log['blockNumber'])['timestamp']

                tx_dict = {
                    'tx_hash': log['transactionHash'].hex(),
                    'from_address': from_address.lower(),
                    'to_address': to_address.lower(),
                    'value': value, # Value in smallest unit (e.g., wei for ETH-like tokens)
                    'block_number': log['blockNumber'],
                    'log_index': log['logIndex'],
                    'timestamp': block_timestamp # Add timestamp
                }
                transactions.append(tx_dict)

            print(f"Found {len(transactions)} PYUSD Transfer events.")
            return transactions

        except Exception as e:
            print(f"Error fetching logs from RPC: {e}")
            return [] # Return empty list on error


    def fetch_transactions_from_rpc_1(self, start_block, end_block, chunk_size=1000):
        """
        Fetches enriched PYUSD Transfer events in chunks using full block inspection
        and receipt parsing for deeper data, including gas info, timestamp, and status.

        Args:
            start_block (int): Starting block number.
            end_block (int): Ending block number.
            chunk_size (int): Block range per batch (default = 1000).

        Returns:
            list: A list of enriched PYUSD transfer dictionaries.
        """
        print(f"Fetching PYUSD transfers in chunks from block {start_block} to {end_block} (chunk size: {chunk_size})...")
        transfer_event_signature = self.w3.keccak(text="Transfer(address,address,uint256)").hex()
        pyusd_lower = self.pyusd_contract_address.lower()

        all_transfers = []
        current_block = start_block

        while current_block <= end_block:
            chunk_end = min(current_block + chunk_size - 1, end_block)
            print(f"  ⏳ Processing blocks {current_block} to {chunk_end}")

            for block_number in range(current_block, chunk_end + 1):
                try:
                    block = self.w3.eth.get_block(block_number, full_transactions=True)
                    timestamp = block.timestamp
                    transactions = block.get("transactions", [])

                    for tx in transactions:
                        if not tx.to or tx.to.lower() != pyusd_lower:
                            continue  # Only inspect transactions to the PYUSD contract

                        try:
                            receipt = self.w3.eth.get_transaction_receipt(tx.hash)
                            for log in receipt.logs:
                                if (
                                    log["address"].lower() == pyusd_lower and
                                    log["topics"][0].hex() == transfer_event_signature and
                                    len(log["topics"]) >= 3
                                ):
                                    from_address = "0x" + log["topics"][1].hex()[-40:]
                                    to_address = "0x" + log["topics"][2].hex()[-40:]
                                    value = self.w3.to_int(hexstr=log["data"].hex())

                                    all_transfers.append({
                                        "tx_hash": tx.hash.hex(),
                                        "from_address": from_address.lower(),
                                        "to_address": to_address.lower(),
                                        "value": value,
                                        "block_number": block_number,
                                        "log_index": log["logIndex"],
                                        "gas": tx["gas"],
                                        "gas_price": self.w3.from_wei(tx["gasPrice"], "gwei"),
                                        "gas_used": receipt["gasUsed"],
                                        "status": receipt["status"],
                                        "timestamp": timestamp,
                                    })

                        except Exception as inner_e:
                            print(f"    ⚠️ Error with tx {tx.hash.hex()}: {inner_e}")

                    time.sleep(0.2)  # avoid hitting rate limits

                except Exception as outer_e:
                    print(f"  ⚠️ Failed to fetch block {block_number}: {outer_e}")

            print(f"  ✅ Chunk complete: blocks {current_block}-{chunk_end}, events found: {len(all_transfers)}")
            current_block = chunk_end + 1

        print(f"✅ Total PYUSD transfers found: {len(all_transfers)}")
        return all_transfers





    def analyze_usage_patterns(self, transactions):
        """
        Analyzes PYUSD transaction data (Transfer events) to infer usage patterns, focusing on web3 activities.

        Args:
            transactions (list): A list of transaction event dictionaries from fetch_transactions_from_rpc.

        Returns:
            dict: A dictionary containing usage insights.  Ensured to have all keys.
        """
        if not transactions:
            return {
                "message": "No transaction data available for analysis.",
                "analysis_period": {
                    "start_block": None,
                    "end_block": None,
                    "start_time_unix": 0,
                    "end_time_unix": 0,
                    "duration_seconds": 0,
                    "duration_days": 0,
                },
                "summary_stats": {
                    "num_transfer_events": 0,
                    "unique_senders": 0,
                    "unique_receivers": 0,
                    "total_value_transferred": "0",
                    "average_transfer_value": "0",
                },
                "web3_activity_distribution": {},
                "web3_activity_percentages": {},
            }

        # 1. Basic Transaction Counts
        num_transactions = len(transactions) # Number of Transfer events
        unique_senders = set(tx["from_address"] for tx in transactions)
        unique_receivers = set(tx["to_address"] for tx in transactions)

        # 2. Value Distribution
        total_value_transferred = sum(tx["value"] for tx in transactions)
        average_value = total_value_transferred / num_transactions if num_transactions else 0

        # 3. Web3 Activity Mapping (Based on known entities)
        web3_activities = defaultdict(int)
        # Define web3 activities and the entities/contracts involved.
        # Make entity names lowercase for consistent matching with loaded data keys.
        web3_activities_categories = {
           
            "CEX Interaction": ["binance", "coinbase", "kraken", "okx", "paxos4", "kucoin"],
            "DEX Interaction": ["uniswap", "sushiswap", "curve"],
            "NFT Platform Interaction": ["opensea", "looksrare", "blur"],
            "DeFi Lending Interaction": ["aave", "compound"],
            "Staking Interaction": ["lido", "rocket_pool", "stakewise"],
            "Bridging Interaction": ["stargate", "hop_protocol", "multichainorg"],
            "Other Identified Entity": [], # Will be populated dynamically
            "Unidentified Interaction": 0, # Counter for interactions with unknown addresses
        
        }
        known_entities_lower = {e.lower() for e in web3_activities_categories} # Flatten list for faster lookup

        interactions_count = 0
        for tx in transactions:
            from_address_lower = tx["from_address"] # Already lowercase from fetch
            to_address_lower = tx["to_address"]     # Already lowercase from fetch

            from_entity = self.address_to_entity.get(from_address_lower)
            to_entity = self.address_to_entity.get(to_address_lower)

            interaction_classified = False

            # Check sender
            if from_entity:
                interactions_count += 1
                entity_lower = from_entity.lower()
                classified = False
                for activity, entities in web3_activities_categories.items():
                    if activity == "Unidentified Interaction": continue # Skip the counter key
                    if entity_lower in [e.lower() for e in entities]: # Ensure comparison list is lowercase
                        web3_activities[activity] += 1
                        classified = True
                        break
                if not classified:
                    # If known entity but not in predefined categories, classify as "Other Identified Entity"
                    web3_activities["Other Identified Entity"] += 1
                    # Optionally add the specific entity name to the category list dynamically if needed
                    # if entity_lower not in web3_activities_categories["Other Identified Entity"]:
                    #     web3_activities_categories["Other Identified Entity"].append(entity_lower)
                interaction_classified = True

            # Check receiver
            if to_entity:
                interactions_count += 1
                entity_lower = to_entity.lower()
                classified = False
                for activity, entities in web3_activities_categories.items():
                    if activity == "Unidentified Interaction": continue
                    if entity_lower in [e.lower() for e in entities]:
                        web3_activities[activity] += 1
                        classified = True
                        break
                if not classified:
                    web3_activities["Other Identified Entity"] += 1
                interaction_classified = True

            # If neither sender nor receiver is a known entity
            if not interaction_classified:
                web3_activities["Unidentified Interaction"] += 1
                interactions_count += 1 # Count as one interaction if both are unknown

        # Calculate percentages
        activity_percentages = {
            activity: (count / interactions_count * 100) if interactions_count else 0
            for activity, count in web3_activities.items()
        }


        # 4. Temporal Analysis
        start_time = min(tx["timestamp"] for tx in transactions) if transactions else 0
        end_time = max(tx["timestamp"] for tx in transactions) if transactions else 0
        duration_seconds = end_time - start_time if transactions else 0
        duration_days = duration_seconds / 86400

        results =  {
            "analysis_period": {
                "start_block": min(tx["block_number"] for tx in transactions) if transactions else None,
                "end_block": max(tx["block_number"] for tx in transactions) if transactions else None,
                "start_time_unix": start_time,
                "end_time_unix": end_time,
                "duration_seconds": duration_seconds,
                "duration_days": round(duration_days, 2),
            },
            "summary_stats": {
                "num_transfer_events": num_transactions,
                "unique_senders": len(unique_senders),
                "unique_receivers": len(unique_receivers),
                "total_value_transferred": str(total_value_transferred), # Keep as string for large numbers
                "average_transfer_value": str(average_value),
            },
            "web3_activity_distribution": dict(web3_activities),
            "web3_activity_percentages": {
                act: round(perc, 2) for act, perc in activity_percentages.items()
            }
        }
        return results
