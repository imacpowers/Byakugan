# Byakugan: Analysis Suite

## Overview

Byakugan is a Flask-based web application designed to provide insights into specific activities and conditions on the Ethereum blockchain. It currently focuses on analyzing usage patterns of the PYUSD stablecoin, real-time network congestion factors, and assessing potentially safer periods for executing transactions based on recent network activity.

This tool is intended for developers, analysts, or enthusiasts interested in monitoring specific aspects of Ethereum network health and token flows.

## Features

* **PYUSD Usage Analysis:** Analyze historical PYUSD `Transfer` events within a specified timeframe (e.g., last 24 hours, last 7 days) to understand:
    * Total transfer volume and count.
    * Unique sender and receiver addresses.
    * Average transfer value.
    * Distribution of activity across known Web3 entity types (CEX, DEX, DeFi, etc.) based on a configurable entity mapping. [cite: uploaded:codeF/usage_analyzer.py]
* **Network Congestion Analysis:** Provides a real-time snapshot of the latest Ethereum block to assess network congestion, highlighting:
    * Block gas usage percentage.
    * Total transaction count and count of transactions involving PYUSD.
    * Average PYUSD transaction count over a recent window.
    * Heuristically identified causes for congestion (e.g., high gas usage, potential MEV activity, potential flashloan activity). [cite: provided in user query context]
    * Lists of suspected MEV and flashloan transaction hashes within the block.
    * *(Includes auto-refresh functionality via JavaScript to keep data current).*
* **Safe Period Analysis:** Assesses recent blockchain activity (multiple blocks) to determine potentially "safer" or "riskier" periods for submitting complex transactions, considering factors like:
    * Recent transaction volume and gas price spikes (as a proxy for mempool activity). [cite: uploaded:codeF/safe_periods.py]
    * Involvement of known entities (e.g., MEV bots, CEXes) in recent blocks. [cite: uploaded:codeF/safe_periods.py]
    * Provides a simple risk level assessment (e.g., Low Risk, High Risk) and a recommendation. [cite: uploaded:codeF/safe_periods.py]

## Technology Stack

* **Backend:** Python, Flask
* **Blockchain Interaction:** Web3.py
* **HTTP Requests:** Requests (used internally by Web3.py and potentially for direct RPC calls)
* **Frontend:** HTML, CSS, JavaScript, Jinja2 Templating
* **Charting (Optional):** Chart.js (if chart sections are enabled in templates)
* **Data:** JSON (for entity mapping)

## Project Structure
```
Byakugan/
│
├── app/                     # Main Flask application package
│   ├── init.py          # Initializes Flask app, blueprints, configs
│   ├── routes.py            # Defines web routes for dashboards
│   │
│   ├── services/            # Business logic modules
│   │   ├── init.py
│   │   ├── usage_analysis_service.py    # PYUSDUsageAnalyzer logic
│   │   ├── congestion_analysis_service.py # CongestionAnalyzer logic
│   │   └── safe_period_analysis_service.py  # SafePeriodAnalyzer logic
│   │
│   ├── templates/           # HTML Templates
│   │   ├── base1.html       # Base template
│   │   ├── usage_analysis_dashboard.html
│   │   ├── congestion_analysis_dashboard.html
│   │   └── safe_period_analysis_dashboard.html
│   │
│   ├── static/              # Static files (CSS, JS)
│   │   ├── css/
│   │   └── js/
│   │
│   ├── utils.py             # Utility functions (e.g., moving_average)
│   └── config.py            # Application configuration class
│
├── data/                    # Data files used by the application
│   └── entity_data.json     # Address-to-entity mapping file
│
├── venv/                    # Virtual environment directory (ignored by git)
│
├── run.py                   # Script to run the Flask development server
├── requirements.txt         # Python dependencies
├── .gitignore               # Specifies intentionally untracked files
└── README.md                # This file
```
## Setup Instructions

1.  **Prerequisites:**
    * Python 3.10+ recommended
    * Git

2.  **Clone Repository:**
    ```bash
    git clone [https://github.com/imacpowers/Byakugan.git](https://github.com/imacpowers/Byakugan.git)
    cd Byakugan
    ```

3.  **Create Virtual Environment:**
    ```bash
    python -m venv venv
    # Activate (Linux/macOS)
    source venv/bin/activate
    # Activate (Windows - Command Prompt)
    # venv\Scripts\activate.bat
    # Activate (Windows - PowerShell)
    # venv\Scripts\Activate.ps1
    ```

4.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

5.  **Configuration (`config.py` file):**
    * **Important:** Configuration variables are set directly within the `config.py` file (or `app/config.py` depending on your structure). Open this file in a text editor.
    * **Edit the necessary variables** within the `Config` class, especially:
        * `GCP_RPC_URL`: **REQUIRED**. Replace the placeholder or default value with your actual Ethereum Mainnet JSON-RPC endpoint URL (including any necessary API keys).
        * `PYUSD_CONTRACT_ADDRESS`: Verify this is the correct, current checksummed address for the PYUSD token you want to analyze.
        * `ENTITY_DATA_PATH`: Ensure this points correctly to your `entity_data.json` file (e.g., `'data/entity_data.json'`).
        * `SECRET_KEY`: **Change the default value** to a strong, random secret key for Flask session security. You can generate one using Python: `python -c 'import os; print(os.urandom(24))'`
        * Review and adjust other configuration variables within the file as needed (e.g., addresses for DEX Routers, Flashloan contracts, `CONGESTION_WINDOW_SIZE`).

6.  **Entity Data (`data/entity_data.json`):**
    * Ensure the `data/` directory exists in the project root.
    * Create or place your `entity_data.json` file inside the `data/` directory. This file maps Ethereum addresses (lowercase recommended) to known entity names.
    * Example Format:
        ```json
        {
          "0x742d35cc6634c0532925a3b844bc454e4438f44e": "Binance: Hot Wallet 1",
          "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": "Binance: Hot Wallet 2",
          "0x6c3e409e08060992d36d62a6e8ca077e786f179f": "PayPal: PYUSD Contract",
          "0x7a250d5630b4cf539739df2c5acb4c659f2488d9": "Uniswap V2: Router 2",
          "0x...": "Known DeFi Protocol X"
        }
        ```

7.  **Run the Application:**
    ```bash
    flask run
    # Or if using run.py directly:
    # python run.py
    ```
    * The application should be accessible at `http://127.0.0.1:5001` (or the port specified in `run.py`).

## Usage Instructions

1.  **Access Dashboards:** Open your web browser and navigate to the application's running address (e.g., `http://127.0.0.1:5001`). Use the navigation bar (assuming one exists in `base1.html`) to access the different analysis dashboards.

2.  **Usage Analysis Dashboard (`/usage-analysis`):**
    * This dashboard analyzes PYUSD transfers over a period you select.
    * Enter a duration (e.g., `24`) and select a unit (Minutes, Hours, Days).
    * Click "Analyze".
    * The dashboard displays:
        * The block range analyzed.
        * Summary statistics (total transfers, unique addresses, total/average value).
        * A table breaking down the percentage and count of transfers involving known Web3 entity types (CEX, DEX, DeFi, etc.).

3.  **Congestion Analysis Dashboard (`/congestion-analysis`):**
    * This dashboard shows an analysis of the *latest* Ethereum block fetched when the page loads.
    * It displays:
        * Current block number and timestamp.
        * Gas usage percentage (color-coded for high usage).
        * Total transactions and PYUSD-involved transactions in the block.
        * Average PYUSD transaction count over a recent window.
        * A list of identified congestion causes (e.g., "High Block Gas Usage", "Potential MEV Activity").
        * Lists of transaction hashes suspected to be related to flashloans or MEV activity, linked to Etherscan.
    * The page automatically refreshes periodically (e.g., every 30 seconds) to show data for the new latest block. You can also use the manual "Refresh Data" button.

4.  **Safe Period Analysis Dashboard (`/safe-period-analysis`):**
    * This dashboard assesses recent network activity (looking back over several blocks) to provide a risk indication for submitting complex transactions.
    * It displays:
        * A risk level assessment ("Low Risk", "High Risk", "Moderate Risk", or "Insufficient Data").
        * A brief recommendation (e.g., "Potentially safer period..." or "Delay complex transactions...").
        * Supporting indicators related to recent mempool activity (based on gas/tx data) and known entity involvement (MEV bots, CEXes).

## How It Works

* **Usage Analysis:** Queries the configured Ethereum RPC node using `eth_getLogs` (or iterates blocks/receipts depending on the method called) to find all `Transfer` events for the specified token address within the calculated block range. It aggregates statistics and uses the `entity_data.json` mapping to categorize interactions with known addresses. [cite: uploaded:codeF/usage_analyzer.py]
* **Congestion Analysis:** Fetches the latest block number and then the full block details (including transactions). It calculates the gas usage ratio and analyzes the transactions within the block for specific patterns: presence of PYUSD, interactions with known flashloan contracts, or high priority fees potentially indicating MEV. [cite: provided in user query context] It uses a moving average for recent PYUSD transaction counts.
* **Safe Period Analysis:** Fetches data for a recent window of blocks. It analyzes this data to calculate proxies for mempool activity (e.g., average gas price, transaction count) and checks for transactions involving known entities listed in `entity_data.json` (especially MEV bots or major exchanges) to determine a heuristic-based risk score. [cite: uploaded:codeF/safe_periods.py]

## Configuration

Key configuration options are set **within the `config.py` file**:

* `GCP_RPC_URL`: **Required.** Your Ethereum Mainnet JSON-RPC endpoint URL.
* `PYUSD_CONTRACT_ADDRESS`: The contract address for the PYUSD token being analyzed.
* `ENTITY_DATA_PATH`: Path to the JSON file mapping addresses to names.
* `SECRET_KEY`: Used by Flask for session security. Should be changed from any default value.
* `CONGESTION_WINDOW_SIZE`: (Used by Congestion Analyzer) The number of blocks to consider for moving averages.
* *(Other addresses like DEX Routers, Flashloan Contracts are likely defined within `config.py` or service files if used by heuristics).*

## Contributing

* pull requests are welcome, issue reporting is welcome.*

## License

This project is licensed under the **Apache License, Version 2.0**. See the `LICENSE` file (you should create one with the Apache 2.0 text) for details or visit [https://www.apache.org/licenses/LICENSE-2.0](https://www.apache.org/licenses/LICENSE-2.0).

Sources and related content

