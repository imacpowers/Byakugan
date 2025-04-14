# app/services/safe_period_analysis_service.py
import time
import json
import statistics
from collections import defaultdict, deque
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from pathlib import Path

# Logic derived from safe_periods.py

class SafePeriodAnalyzer:
    """
    Analyzes recent blockchain data to identify potentially safer periods for
    complex transactions, considering factors like MEV activity and network congestion.
    """

    def __init__(self, config):
        """
        Initializes the analyzer with the Flask configuration object.

        Args:
            config (object): Flask configuration object with RPC_URL, ENTITY_DATA_FILE, etc.
        """
        self.config = config
        self.w3 = Web3(HTTPProvider(config['GCP_RPC_URL']))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to RPC: {config['GCP_RPC_URL']}")

        self.entity_data = self.load_entity_data(config['ENTITY_DATA_FILE'])
        # Store recent block data *within the instance*. Consider a cache for multi-user apps.
        self.recent_blocks_data = deque(maxlen=config['SAFE_PERIOD_BLOCK_HISTORY_LENGTH'])
        self.history_length = config['SAFE_PERIOD_BLOCK_HISTORY_LENGTH']
        self.min_blocks_for_analysis = config['SAFE_PERIOD_MIN_BLOCKS_FOR_ANALYSIS']
        # Use entity_data loaded above directly
        self.address_to_entity = self.entity_data # Renamed for clarity

    def load_entity_data(self, entity_data_file):
        """Loads mapping of Ethereum addresses (lowercase) to known entities."""
        try:
            with open(entity_data_file, "r") as f:
                loaded_data = json.load(f)
                # Ensure keys (addresses) are lowercase
                return {addr.lower(): entity for addr, entity in loaded_data.items()}
        except FileNotFoundError:
            print(f"Warning: Entity data file not found at {entity_data_file}. Safe period analysis may be less accurate.")
            return {}
        except json.JSONDecodeError as e:
            print(f"Warning: Could not decode JSON from entity data file {entity_data_file}: {e}.")
            return {}
        except Exception as e:
             print(f"Warning: An unexpected error occurred loading entity data: {e}")
             return {}

    def fetch_block_data(self, block_identifier):
        """Fetches block data (including transactions) from the RPC."""
        try:
            block = self.w3.eth.get_block(block_identifier, full_transactions=True)
            # Convert to standard dict
            return json.loads(Web3.to_json(block))
        except Exception as e:
            print(f"Error fetching block {block_identifier}: {e}")
            return None

    def update_recent_blocks(self):
        """
        Updates the internal list of recent blocks, fetching necessary data.
        Avoids re-fetching blocks already in the deque.
        """
        try:
            latest_block_number = self.w3.eth.block_number
            start_block = latest_block_number - self.history_length + 1

            # Determine which blocks need fetching
            existing_block_numbers = {b['number'] for b in self.recent_blocks_data}
            needed_blocks = [
                num for num in range(start_block, latest_block_number + 1)
                if num not in existing_block_numbers and num > 0 # Ensure block number is positive
            ]

            if not needed_blocks:
                 # Prune old blocks if needed
                 while len(self.recent_blocks_data) > 0 and self.recent_blocks_data[0]['number'] < start_block:
                     self.recent_blocks_data.popleft()
                 return # No new blocks to fetch beyond pruning

            print(f"Fetching {len(needed_blocks)} new blocks for safe period analysis (Range: {needed_blocks[0]}-{needed_blocks[-1]})")

            fetched_blocks = []
            for block_num in needed_blocks:
                 block_data = self.fetch_block_data(block_num)
                 if block_data:
                     fetched_blocks.append(block_data)
                 else:
                      print(f"Warning: Failed to fetch block {block_num}, skipping.")

            # Add fetched blocks and sort (deque doesn't guarantee order if added out of sequence)
            for block in fetched_blocks:
                 self.recent_blocks_data.append(block)

            # Ensure deque is sorted by block number and pruned
            sorted_blocks = sorted(list(self.recent_blocks_data), key=lambda b: b['number'])
            self.recent_blocks_data.clear()
            # Add only the last 'history_length' blocks back
            self.recent_blocks_data.extend(sorted_blocks[-self.history_length:])

            print(f"Updated recent blocks. Current history size: {len(self.recent_blocks_data)}")

        except Exception as e:
            print(f"Error updating recent blocks: {e}")


    def analyze_congestion_proxy(self):
        """
        Analyzes recent block data as a proxy for network congestion and gas price volatility.
        """
        if len(self.recent_blocks_data) < self.min_blocks_for_analysis:
            return {"error": "Insufficient recent block data for congestion analysis."}

        total_transactions = 0
        total_gas_used = 0
        gas_prices = [] # Collect base fees or effective gas prices
        block_gas_usage_ratios = []

        for block in self.recent_blocks_data:
            total_transactions += len(block.get('transactions', []))
            block_gas_used = int(block.get('gasUsed', 0))
            block_gas_limit = int(block.get('gasLimit', 1)) # Avoid division by zero
            total_gas_used += block_gas_used
            block_gas_usage_ratios.append(block_gas_used / block_gas_limit if block_gas_limit > 0 else 0)

            # Collect base fee per gas for EIP-1559 blocks
            base_fee = block.get('baseFeePerGas')
            if base_fee is not None:
                 gas_prices.append(int(base_fee))
            else:
                 # Fallback: Average gas price from legacy transactions in the block
                 legacy_prices = [int(tx.get('gasPrice', 0)) for tx in block.get('transactions', []) if tx.get('type', '0x0') in ['0x0', 0]]
                 if legacy_prices:
                     gas_prices.append(sum(legacy_prices) / len(legacy_prices))


        avg_gas_price = sum(gas_prices) / len(gas_prices) if gas_prices else 0
        max_gas_price = max(gas_prices) if gas_prices else 0
        gas_price_std_dev = statistics.stdev(gas_prices) if len(gas_prices) > 1 else 0
        avg_block_gas_usage = sum(block_gas_usage_ratios) / len(block_gas_usage_ratios) if block_gas_usage_ratios else 0

        return {
            "average_transactions_per_block": total_transactions / len(self.recent_blocks_data),
            "average_base_fee_gwei": round(avg_gas_price / 1e9, 2),
            "max_base_fee_gwei": round(max_gas_price / 1e9, 2),
            "base_fee_std_dev_gwei": round(gas_price_std_dev / 1e9, 2),
            "average_block_gas_usage_ratio": round(avg_block_gas_usage, 3),
            "blocks_analyzed": len(self.recent_blocks_data),
        }

    def analyze_entity_involvement(self):
        """
        Analyzes the involvement of known entities (e.g., MEV bots, exchanges) in recent transactions.
        Requires a well-defined entity mapping.
        """
        if len(self.recent_blocks_data) < self.min_blocks_for_analysis:
            return {"error": "Insufficient recent block data for entity analysis."}

        involved_entity_counts = defaultdict(int)
        # Define categories based on your entity_data.json structure and knowledge
        
        mev_related_entities = {"flashbots", "bloxroute", "eden network"} # Lowercase
        exchange_entities = {"binance", "coinbase", "kraken", "gemini"} # Lowercase
        other_known_entities = set(self.address_to_entity.values()) - mev_related_entities - exchange_entities

        mev_tx_count = 0
        cex_tx_count = 0
        other_entity_tx_count = 0
        total_entity_interactions = 0

        for block in self.recent_blocks_data:
            for tx in block.get('transactions', []):
                from_address = tx.get('from', '').lower() if tx.get('from') else ''
                to_address = tx.get('to', '').lower() if tx.get('to') else ''

                from_entity = self.address_to_entity.get(from_address)
                to_entity = self.address_to_entity.get(to_address)

                interacted = False
                # Check sender
                if from_entity:
                    interacted = True
                    entity_lower = from_entity.lower()
                    if entity_lower in mev_related_entities:
                        mev_tx_count += 1
                    elif entity_lower in exchange_entities:
                        cex_tx_count += 1
                    else: # Other known entity
                         other_entity_tx_count +=1

                # Check receiver (avoid double counting if both are known)
                if to_entity and to_entity != from_entity: # Prevent double count if sending to self/same entity type
                     interacted = True
                     entity_lower = to_entity.lower()
                     if entity_lower in mev_related_entities and from_entity not in mev_related_entities : # Avoid double count if both MEV
                         mev_tx_count += 1
                     elif entity_lower in exchange_entities and from_entity not in exchange_entities: # Avoid double count if both CEX
                         cex_tx_count += 1
                     elif entity_lower in other_known_entities and from_entity not in other_known_entities : # Avoid double count if both other known
                          other_entity_tx_count +=1
                elif to_entity and to_entity == from_entity: # Count interaction once if sender/receiver is same known entity
                    pass # Already counted via sender check


                if interacted:
                     total_entity_interactions += 1


        return {
            "mev_related_tx_count": mev_tx_count,
            "cex_related_tx_count": cex_tx_count,
            "other_known_entity_tx_count": other_entity_tx_count,
            "total_entity_interactions": total_entity_interactions,
             "blocks_analyzed": len(self.recent_blocks_data),
        }

    def assess_safe_period(self):
        """
        Assesses the safety of the current period based on recent block data analysis.

        Returns:
            dict: A dictionary containing a safety assessment ('Low Risk', 'Moderate Risk',
                  'High Risk', 'Insufficient Data') and supporting indicators.
        """
        self.update_recent_blocks() # Ensure data is fresh

        if len(self.recent_blocks_data) < self.min_blocks_for_analysis:
            return {
                "safety_level": "Insufficient Data",
                "recommendation": f"Need at least {self.min_blocks_for_analysis} recent blocks for analysis (currently have {len(self.recent_blocks_data)}).",
                "details": {}
            }

        congestion = self.analyze_congestion_proxy()
        entity_activity = self.analyze_entity_involvement()

        # Combine results for assessment
        details = {
            "congestion_proxy": congestion,
            "entity_activity": entity_activity,
        }

        # --- Heuristic-based Safety Assessment ---
        # Define risk thresholds 
        high_risk_gas_gwei = 100
        moderate_risk_gas_gwei = 50
        high_risk_gas_std_dev_gwei = 20 # High volatility
        high_risk_block_usage = 0.90
        moderate_risk_block_usage = 0.75
        high_risk_mev_tx_count = 10 # Per history window
        moderate_risk_mev_tx_count = 5

        risk_score = 0

        # Congestion Risks
        avg_gas = congestion.get("average_base_fee_gwei", 0)
        gas_std_dev = congestion.get("base_fee_std_dev_gwei", 0)
        avg_block_usage = congestion.get("average_block_gas_usage_ratio", 0)

        if avg_gas > high_risk_gas_gwei or gas_std_dev > high_risk_gas_std_dev_gwei:
            risk_score += 2
        elif avg_gas > moderate_risk_gas_gwei:
            risk_score += 1

        if avg_block_usage > high_risk_block_usage:
            risk_score += 2
        elif avg_block_usage > moderate_risk_block_usage:
            risk_score += 1

        # MEV Risks
        mev_count = entity_activity.get("mev_related_tx_count", 0)
        if mev_count > high_risk_mev_tx_count:
            risk_score += 2
        elif mev_count > moderate_risk_mev_tx_count:
            risk_score += 1

        # Determine Safety Level
        if risk_score >= 4:
            safety_level = "High Risk"
            recommendation = "High congestion and/or MEV activity detected. Delay complex/sensitive transactions."
        elif risk_score >= 2:
            safety_level = "Moderate Risk"
            recommendation = "Elevated congestion or MEV activity. Proceed with caution, consider higher gas."
        else:
            safety_level = "Low Risk"
            recommendation = "Network conditions appear relatively stable. Safer period for transactions."


        return {
            "safety_level": safety_level,
            "recommendation": recommendation,
            "risk_score": risk_score, # Optional: expose score
            "details": details
        }

