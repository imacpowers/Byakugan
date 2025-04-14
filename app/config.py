# app/config.py
import os

class Config:
    """Base configuration settings."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-very-secret-key'

    # --- Settings derived from your scripts ---

    # GCP RPC Endpoint (Update with your actual URL)
    GCP_RPC_URL = "https://blockchain.googleapis.com/v1/projects/advance-display-433704-a6/locations/us-central1/endpoints/ethereum-mainnet/rpc?key=ADD YOUR API KEY" # Replace with your actual GCP RPC URL and Key

    # PYUSD Contract Address (Ensure this is correct)
    PYUSD_CONTRACT_ADDRESS_1 = "0x6b4c7a5e3f0b99c74a6b515f1915ad0f23844d83" # From cong_real.py
    PYUSD_CONTRACT_ADDRESS = "0x6c3ea9036406852006290770BEdFcAbA0e23A0e8"
    

    # Entity Data File Path
    ENTITY_DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'entity_data_file.json')

    # Static Analysis Defaults (Update paths if necessary)
    DEFAULT_CONTRACT_PATH = "contracts/PYUSD.sol" # Example path from staticanalysis.py
    DEFAULT_ABI_PATH = "contracts/PYUSD.abi" # Example path from staticanalysis.py

    # Congestion Analysis Settings
    CONGESTION_WINDOW_SIZE = 100 # From cong_real.py
    GAS_PRICE_SPIKE_THRESHOLD = 3 # From cong_real.py
    AAVE_FLASHLOAN_CONTRACT = "0x794a61358d4152756365ebf49212413e16e5e575" # From cong_real.py
    BALANCER_FLASHLOAN_CONTRACT = "0xba122960e5799694c2b9532758617c12c9fdd07e" # From cong_real.py
    DYDX_FLASHLOAN_CONTRACT = "0x041d6a4131b79695e646816259508525f381481e" # From cong_real.py
    UNISWAP_ROUTER_CONTRACT = "0x7a250d5630b4cf539739df2c5acb4c659f2488d9" # From cong_real.py
    SUSHISWAP_ROUTER_CONTRACT = "0xd9e1ee17e80688b2968f37ff98074f69e3ed864a" # From cong_real.py
    CURVE_ROUTER_CONTRACT = "0xc5bdd66638370fb5c88a3129f11c5344a82d371c" # From cong_real.py
    DEX_ROUTERS = [
        UNISWAP_ROUTER_CONTRACT,
        SUSHISWAP_ROUTER_CONTRACT,
        CURVE_ROUTER_CONTRACT
    ] # From cong_real.py

    # Safe Period Analysis Settings
    SAFE_PERIOD_BLOCK_HISTORY_LENGTH = 20 # From safe_periods.py
    SAFE_PERIOD_MIN_BLOCKS_FOR_ANALYSIS = 5 # From safe_periods.py

    # Usage Analysis Settings
    # Add any specific config needed for usage analysis if different from above

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    # Add any production-specific settings

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}