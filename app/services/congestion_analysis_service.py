# app/services/congestion_analysis_service.py
import requests
import time
import json
from datetime import datetime
from collections import defaultdict, deque
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.exceptions import Web3Exception, TransactionNotFound
from app.utils import moving_average # Import from local utils

# Logic derived from cong_real.py

class CongestionAnalyzer:
    """Analyzes Ethereum block data for congestion patterns, focusing on PYUSD activity."""

    def __init__(self, config):
        """
        Initializes the analyzer with configuration.

        Args:
            config (object): Flask configuration object containing necessary settings
                             (e.g., GCP_RPC_URL, PYUSD_CONTRACT_ADDRESS, DEX_ROUTERS etc.)
        """
        self.config = config
        self.w3 = Web3(HTTPProvider(config['GCP_RPC_URL']))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {config['GCP_RPC_URL']}")

        self.pyusd_contract_address_lower = config['PYUSD_CONTRACT_ADDRESS'].lower()
        self.dex_routers_lower = [r.lower() for r in config['DEX_ROUTERS']]
        self.flashloan_contracts_lower = [
            config['AAVE_FLASHLOAN_CONTRACT'].lower(),
            config['BALANCER_FLASHLOAN_CONTRACT'].lower(),
            config['DYDX_FLASHLOAN_CONTRACT'].lower(),
        ]

        # Historical data (consider managing state more robustly in a real app)
        self.recent_event_tx_counts = deque(maxlen=config['CONGESTION_WINDOW_SIZE'])
        self.recent_event_gas_used = deque(maxlen=config['CONGESTION_WINDOW_SIZE'])


    def get_latest_block_number(self):
        """Fetches the latest block number."""
        try:
            return self.w3.eth.block_number
        except Exception as e:
            print(f"Error fetching latest block number: {e}")
            return None

    def get_block_details(self, block_identifier):
        """Fetches detailed information about a specific block."""
        try:
            # block_identifier can be block number or hash
            block = self.w3.eth.get_block(block_identifier, full_transactions=True)
            # Convert AttributeDicts to regular dicts for easier handling/JSON serialization
            return json.loads(Web3.to_json(block))
        except Exception as e:
            print(f"Error fetching block details for {block_identifier}: {e}")
            return None

    def get_transaction_details(self, tx_hash):
        """Fetches details for a specific transaction."""
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            return json.loads(Web3.to_json(tx))
        except TransactionNotFound:
             print(f"Transaction not found: {tx_hash}")
             return None
        except Exception as e:
            print(f"Error fetching transaction details for {tx_hash}: {e}")
            return None

    def get_trace_transaction(self, tx_hash):
        """Retrieves a detailed trace of a transaction using debug_traceTransaction."""
        
        try:
            # Directly using w3.provider.make_request as debug_traceTransaction isn't standard web3.py
            trace = self.w3.provider.make_request(
                "debug_traceTransaction",
                [tx_hash, {"disableStorage": True, "disableStack": True, "fullStorage": False}]
            )
            return trace.get('result', {}) # Extract result from JSON-RPC response
        except Exception as e:
            # Catch potential exceptions if method doesn't exist or RPC fails
            print(f"Error tracing transaction {tx_hash} (debug_traceTransaction might be unavailable/failed): {e}")
            return {}

    def analyze_transaction_gas_trace(self, tx_trace):
        """Analyzes the gas consumption within a transaction trace from debug_traceTransaction."""
        gas_usage = defaultdict(int)
        if not isinstance(tx_trace, dict) or 'structLogs' not in tx_trace:
             # Geth trace format might differ, this assumes parity/openethereum like structure or basic dict
             print(f"Warning: Unexpected trace format or no structLogs found.")
             # Attempt basic parsing if 'gasUsed' exists at top level
             top_gas = tx_trace.get('gasUsed', 0)
             if isinstance(top_gas, str) and top_gas.startswith('0x'):
                 top_gas = int(top_gas, 16)
             if top_gas > 0:
                 gas_usage['TOTAL_TRACE_GAS'] = top_gas
             return dict(gas_usage)


        # This parsing assumes geth-style structLogs trace output
        for log_entry in tx_trace.get('structLogs', []):
             op_code = log_entry.get('op')
             gas_cost = log_entry.get('gasCost', 0)
             gas_usage[op_code] += gas_cost

        # Fallback if structLogs parsing yielded nothing but gasUsed exists
        if not gas_usage and tx_trace.get('gasUsed'):
            top_gas = tx_trace.get('gasUsed', 0)
            if isinstance(top_gas, str) and top_gas.startswith('0x'):
                 top_gas = int(top_gas, 16)
            if top_gas > 0:
                 gas_usage['TOTAL_TRACE_GAS'] = top_gas


        return dict(gas_usage)


    def is_pyusd_transaction(self, tx):
        """Checks if a transaction involves the PYUSD contract (case-insensitive)."""
        # Assumes tx is a dictionary derived from web3.py transaction object
        to_address = tx.get("to")
        return to_address and to_address.lower() == self.pyusd_contract_address_lower

    def analyze_block_congestion(self, block_data):
        """
        Analyzes block data dictionary to detect congestion and identify potential causes.
        """
        if not block_data:
            return {"error": "Invalid block data provided."}

        transactions = block_data.get("transactions", [])
        gas_used = int(block_data.get("gasUsed", 0)) # Already int if from get_block_details parsing
        gas_limit = int(block_data.get("gasLimit", 1)) # Avoid division by zero
        block_number = int(block_data.get("number", 0))
        block_timestamp = int(block_data.get("timestamp", 0))

        congestion_causes = set() # Use a set to avoid duplicates
        event_tx_count = 0
        event_gas_used = 0
        total_gas_in_block_txs = 0 # Sum gas from tx receipts if available, otherwise estimate
        pyusd_tx_hashes = []
        suspected_flashloan_txs = []
        suspected_validator_mev_txs = []
        gas_breakdown_summary = defaultdict(int)

        # 1. Check for high block gas usage
        gas_usage_ratio = gas_used / gas_limit if gas_limit > 0 else 0
        if gas_usage_ratio > 0.95:
            congestion_causes.add("High Block Gas Usage (>95%)")

        # 2. Analyze Transactions
        for i, tx in enumerate(transactions):
             tx_hash = tx.get("hash")
             tx_gas = int(tx.get("gas", 0)) # Gas limit for the tx
             tx_gas_price = int(tx.get("gasPrice", 0)) # Legacy tx
             tx_max_fee = int(tx.get("maxFeePerGas", 0)) # EIP-1559
             tx_max_priority = int(tx.get("maxPriorityFeePerGas", 0)) # EIP-1559
             tx_to = tx.get("to", "").lower() if tx.get("to") else ""
             tx_from = tx.get("from", "").lower() if tx.get("from") else ""
             tx_type = int(tx.get("type", 0)) # 0=legacy, 1=eip2930, 2=eip1559

             # --- PYUSD Activity ---
             if tx_to == self.pyusd_contract_address_lower or tx_from == self.pyusd_contract_address_lower : # Check both directions
                 event_tx_count += 1
                 pyusd_tx_hashes.append(tx_hash)
                 
                 # We'll sum actual gas used later if fetching receipts/traces.

             # --- Flashloan Detection ---
             if tx_to in self.flashloan_contracts_lower:
                 # Simple check based on interacting with known flashloan contracts
                 
                 if tx_gas > 500000: # High gas limit might indicate complex flashloan tx
                     congestion_causes.add("Potential Flashloan Activity (High Gas Limit)")
                     suspected_flashloan_txs.append(tx_hash)
                 else:
                      congestion_causes.add("Potential Flashloan Activity (Contract Interaction)")
                      suspected_flashloan_txs.append(tx_hash)


             # --- Validator-Induced Congestion / MEV Detection (Basic Heuristics) ---
             # High priority fee can indicate MEV/front-running attempts
             if tx_type == 2 and tx_max_priority > 5 * 1e9: # Example: > 5 Gwei priority fee
                 congestion_causes.add("Potential MEV Activity (High Priority Fee)")
                 suspected_validator_mev_txs.append(tx_hash)

             # Check if 'from' is a known MEV entity (requires entity data)
             # if tx_from in self.config.get('MEV_BOT_ADDRESSES', []):
             #    congestion_causes.add("Potential MEV Activity (Known Bot)")
             #    suspected_validator_mev_txs.append(tx_hash)



        # Update historical data for moving averages
        self.recent_event_tx_counts.append(event_tx_count)
        # self.recent_event_gas_used.append(event_gas_used) # Only if calculated

        avg_event_tx_count = moving_average(self.recent_event_tx_counts)
        avg_event_gas_used = moving_average(self.recent_event_gas_used)


        # 4. Final Assessment
        if not congestion_causes and gas_usage_ratio < 0.5: # If no specific causes and low usage
             congestion_causes.add("Low Congestion")
        elif not congestion_causes:
             congestion_causes.add("Moderate Congestion / Other") # Default if usage isn't low but no specific cause found

        return {
            "block_number": block_number,
            "timestamp": block_timestamp,
            "gas_used": gas_used,
            "gas_limit": gas_limit,
            "gas_usage_ratio": round(gas_usage_ratio, 3),
            "congestion_causes": sorted(list(congestion_causes)),
            "pyusd_tx_count": event_tx_count,
            "pyusd_tx_hashes": pyusd_tx_hashes,
            #"pyusd_gas_used": event_gas_used, # Include if calculated
            "avg_pyusd_tx_count_window": round(avg_event_tx_count, 2),
            #"avg_pyusd_gas_used_window": round(avg_event_gas_used, 0), # Include if calculated
            "suspected_flashloan_txs": suspected_flashloan_txs,
            "suspected_validator_mev_txs": suspected_validator_mev_txs,
            "transaction_count": len(transactions),
        }
        
    def analyze_block_congestion_ii(block, threshold_gas_used=0.95, threshold_gas_price_gwei=100):
     congestion_events = []

     gas_used_ratio = block['gasUsed'] / block['gasLimit']
     block_timestamp = datetime.utcfromtimestamp(block['timestamp']).isoformat()
     block_number = block['number']

     if gas_used_ratio >= threshold_gas_used:
        for tx_hash in block['transactions']:
            try:
                tx = w3.eth.get_transaction(tx_hash)
                receipt = w3.eth.get_transaction_receipt(tx_hash)

                gas_price_gwei = Web3.from_wei(tx.gasPrice, 'gwei')
                contract_address = receipt.contractAddress if receipt.contractAddress else None

                # Heuristic tags (can be expanded later)
                congestion_type = "validator-induced" if gas_price_gwei > threshold_gas_price_gwei else "normal"
                gas_spike_reason = "high_gas_price" if gas_price_gwei > threshold_gas_price_gwei else "high_gas_usage"

                congestion_events.append({
                    "block_number": block_number,
                    "timestamp": block_timestamp,
                    "transaction_hash": tx_hash.hex(),
                    "from_address": tx['from'],
                    "to_address": tx['to'],
                    "contract_address": contract_address,
                    "gas_used": receipt.gasUsed,
                    "gas_limit": block['gasLimit'],
                    "gas_price": float(gas_price_gwei),
                    "congestion_type": congestion_type,
                    "gas_spike_reason": gas_spike_reason,
                })

            except Exception as e:
                print(f"Error processing tx {tx_hash.hex()}: {e}")
                continue

     return congestion_events    
    


    
