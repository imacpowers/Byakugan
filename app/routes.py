# app/routes.py
from flask import render_template, Blueprint, current_app, request, jsonify
import os
import logging
from flask import Flask
#import os
from datetime import datetime, timedelta
from web3 import Web3
from web3.providers.rpc import HTTPProvider
import json
import time
from threading import Thread, Lock  # Import Thread and Lock

# Import service classes
from app.services.static_analysis_service import SmartContractAnalyzer, StaticAnalysisError
from .services.usage_analysis_service import PYUSDUsageAnalyzer
from .services.congestion_analysis_service import CongestionAnalyzer
from .services.safe_period_analysis_service import SafePeriodAnalyzer
from flask import redirect, url_for, flash
from .services.token_trace_service import TokenTraceService # Import the service


main = Blueprint('main', __name__)

# Configuration
GCP_RPC_URL = "https://blockchain.googleapis.com/v1/projects/advance-display-433704-a6/locations/us-central1/endpoints/ethereum-mainnet/rpc?key=ADD YOUR API KEY"  # Replace with your GCP RPC URL
ENTITY_DATA_FILE = "app/data/entity_data_file.json"  # Path to entity mapping file
MAX_BLOCK_RANGE = 5000  # Maximum block range allowed for queries
DEFAULT_BLOCK_RANGE = 100  # Default block range if none is provided
PYUSD_CONTRACT_ADDRESS = "0x6b4c7a5e3f0b99c74a6b515f191c962251432f83"  # Add the PYUSD contract address here


data_cache = {}
cache_lock = Lock()  # Use a lock to protect the cache
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper Functions
def get_block_range_from_timeframe(timeframe):
    """
    Calculates the block range based on the provided timeframe.

    Args:
        timeframe (str): The timeframe string (e.g., "24h", "7d", "yesterday", "today", "last_week").

    Returns:
        tuple: (start_block, end_block) or (None, None) on error.
    """
    try:
        w3 = Web3(HTTPProvider(GCP_RPC_URL))
        latest_block = w3.eth.block_number
        now = datetime.utcnow()

        if timeframe == "yesterday":
            end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = end_time - timedelta(days=1)
        elif timeframe == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif timeframe == "last_week":
            end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_time = end_time - timedelta(days=7)
        elif timeframe.endswith("h"):  # e.g., "24h"
            hours = int(timeframe[:-1])
            end_time = now
            start_time = now - timedelta(hours=hours)
        elif timeframe.endswith("d"):  # e.g., "7d"
            days = int(timeframe[:-1])
            end_time = now
            start_time = now - timedelta(days=days)
        elif timeframe.endswith("m"): #e.g. 30m
            minutes = int(timeframe[:-1])
            end_time = now
            start_time = now - timedelta(minutes=minutes)
        else:
            return None, None  # Invalid timeframe

        start_block = find_closest_block(start_time)
        end_block = find_closest_block(end_time)
        return start_block, end_block

    except Exception as e:
        print(f"Error calculating block range: {e}")
        return None, None

def find_closest_block(target_time):
    """
    Finds the block number whose timestamp is closest to the target time.

    Args:
        target_time (datetime): The target datetime.

    Returns:
        int: The block number, or None on error.
    """
    web3 = Web3(HTTPProvider(GCP_RPC_URL))
    latest_block = web3.eth.block_number
    low = 0
    high = latest_block
    closest_block = latest_block

    while low <= high:
        mid = (low + high) // 2
        block = web3.eth.get_block(mid)
        block_time = datetime.utcfromtimestamp(block.timestamp)

        if abs((block_time - target_time).total_seconds()) < abs((datetime.utcfromtimestamp(web3.eth.get_block(closest_block).timestamp) - target_time).total_seconds()):
            closest_block = mid

        if block_time < target_time:
            low = mid + 1
        else:
            high = mid - 1
    return closest_block


def fetch_and_cache_data(data_key, fetch_function, *args, **kwargs):
    """
    Fetches data using the provided function.  Removed caching.

    Args:
        data_key (str): Key to store the data (not used anymore).
        fetch_function (callable): Function to fetch the data.
        *args: Arguments to pass to the fetch function.
        **kwargs: Keyword arguments to pass to the fetch function.
    """
    data = fetch_function(*args, **kwargs)
    return data



# --- Dashboard Route ---
@main.route('/')
def index():
    """Main dashboard page."""
    # You might want to pass some summary data here eventually
    return render_template('dashboard.html', title="Main Dashboard")


# --- Static Analysis Route ---
@main.route('/static-analysis', methods=['GET', 'POST'])
def static_analysis():
    """Static analysis page that supports both file uploads and contract addresses."""
    results = None
    error = None
    contract_path = None
    contract_address = None

    if request.method == 'POST':
        # Check which input method was selected
        input_type = request.form.get('input_type', 'file')
        
        if input_type == 'file':
            # Handle file upload
            if 'contract_file' not in request.files or request.files['contract_file'].filename == '':
                error = "No file selected for upload."
            else:
                uploaded_file = request.files['contract_file']
                if not uploaded_file.filename.endswith('.sol'):
                    error = "Uploaded file must be a Solidity (.sol) file."
                else:
                    # Save the uploaded file to a temporary location
                    upload_dir = os.path.join(current_app.root_path, 'uploads')
                    os.makedirs(upload_dir, exist_ok=True)
                    file_path = os.path.join(upload_dir, uploaded_file.filename)
                    uploaded_file.save(file_path)
                    contract_path = file_path
        
        elif input_type == 'address':
            # Handle contract address input
            contract_address = request.form.get('contract_address')
            if not contract_address or not contract_address.startswith('0x'):
                error = "Please enter a valid Ethereum contract address."
            else:
                # Create a temporary file for analysis results
                upload_dir = os.path.join(current_app.root_path, 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                contract_path = os.path.join(upload_dir, f"contract_{contract_address}.sol")
                # Create an empty file (will be used for basic analysis)
                with open(contract_path, 'w') as f:
                    f.write("// Placeholder for contract fetched from blockchain")
        
        # Perform analysis if we have a path and no errors
        if contract_path and not error:
            try:
                analyzer = SmartContractAnalyzer(contract_path, rpc_url=current_app.config['GCP_RPC_URL'])
                
                if contract_address and input_type == 'address':
                    # Use get_contract_info to fetch contract details and analyze
                    contract_info = analyzer.get_contract_info(contract_address)
                    if contract_info is None:
                        error = f"Failed to fetch contract details for address: {contract_address}"
                        results = {}
                    else:
                        results = contract_info
                else:
                    # Just analyze the uploaded file
                    analyzer.analyze_contract()
                    results = analyzer.get_analysis_results()
                    
                if results is None:
                    error = "Failed to retrieve analysis results."
                    results = {}
                
            except StaticAnalysisError as e:
                error = str(e)
                results = {}
            except Exception as e:
                error = f"Unexpected error: {str(e)}"
                results = {}

    return render_template('static_analysis_dashboard.html',
                          title="Static Analysis",
                          results=results,
                          error=error,
                          contract_path=contract_path,
                          contract_address=contract_address)
                          


@main.route('/usage-analysis3')
def usage_analysis_3():
    """
    API endpoint for analyzing PYUSD usage patterns.
    Returns either JSON data or renders a dashboard template.
    """
    timeframe = request.args.get('timeframe', '1m')  # Default timeframe
    pyusd_contract_address = current_app.config['PYUSD_CONTRACT_ADDRESS']
    
    start_block, end_block = get_block_range_from_timeframe(timeframe)
    if not start_block or not end_block:
        error = "Invalid timeframe. Use 'yesterday', 'today', or 'last_week', or 'Xh', 'Xd', 'Xm'"
        return render_template('usage_analysis_dashboard.html', title="PYUSD Usage Analysis", 
                               results=None, error=error, start_block=None, end_block=None)
    
    
    total_blocks = end_block - start_block
    use_chunking = True #total_blocks > MAX_BLOCK_RANGE
    chunk_size = 10  # Size for each chunk request
    
    data_key = f"usage_analysis_{timeframe}_{start_block}_{end_block}_{pyusd_contract_address}"
    
    def fetch_usage_data(start_block, end_block, contract_address):
        try:
            analyzer = PYUSDUsageAnalyzer(ENTITY_DATA_FILE, GCP_RPC_URL, contract_address)
            
            # If range is too large, process in chunks manually
            if use_chunking:
                all_transactions = []
                current_block = start_block
                
                while current_block <= end_block:
                    chunk_end = min(current_block + chunk_size - 1, end_block)
                    print(f"Processing chunk from {current_block} to {chunk_end}")
                    
                    # Use the original fetch method which is definitely in the class
                    chunk_transactions = analyzer.fetch_transactions_from_rpc_1(current_block, chunk_end)
                    all_transactions.extend(chunk_transactions)
                    
                    current_block = chunk_end + 1
                
                transactions = all_transactions
            else:
                # Use the original method for smaller ranges
                transactions = analyzer.fetch_transactions_from_rpc_1(start_block, end_block)
                
            usage_data = analyzer.analyze_usage_patterns(transactions)
            print(f"usage_data: {usage_data}")
            return usage_data
        except Exception as e:
            import traceback
            print(f"Error in fetch_usage_data: {str(e)}")
            print(traceback.format_exc())
            return {"error": str(e)}
    return render_template('usage_analysis_dashboard.html', title="PYUSD Usage Analysis", 
                                  results=usage_data, error=error, start_block=start_block, end_block=end_block)        
    
    # fetch_and_cache_data(data_key, fetch_usage_data, start_block, end_block, pyusd_contract_address)
    
    # with cache_lock:
    #     cached_data = data_cache.get(data_key)
    #     print(f"Error in cached_data: {cached_data}")
    #     if cached_data:
    #         results = cached_data["data"]
    #         error = None
    #         print(f"results: {results}")
    #         return render_template('usage_analysis_dashboard.html', title="PYUSD Usage Analysis", 
    #                               results=results, error=error, start_block=start_block, end_block=end_block)
    #     else:
    #         error = "Analysis in progress. Please try again later, no cached data"
    #         return render_template('usage_analysis_dashboard.html', title="PYUSD Usage Analysis", 
    #                               results=None, error=error, start_block=start_block, end_block=end_block)  
    
                             

# --- Usage Analysis Route ---
@main.route('/usage-analysis_1')

def usage_analysis_1():
    """
    API endpoint for analyzing PYUSD usage patterns.  Returns JSON data.
    """
    timeframe = request.args.get('timeframe', 'yesterday')  # Default timeframe
    pyusd_contract_address = current_app.config['PYUSD_CONTRACT_ADDRESS']

    start_block, end_block = get_block_range_from_timeframe(timeframe)
    if not start_block or not end_block:
        return jsonify({"error": "Invalid timeframe. Use 'yesterday', 'today', or 'last_week', or 'Xh', 'Xd', 'Xm'"}), 400
    if (end_block - start_block) > MAX_BLOCK_RANGE:
        return jsonify({"error": f"Block range exceeds maximum allowed ({MAX_BLOCK_RANGE} blocks)."}), 400

    data_key = f"usage_analysis_{timeframe}_{start_block}_{end_block}_{pyusd_contract_address}"

    def _fetch_usage_data(start_block, end_block, contract_address):
        try:
            analyzer = PYUSDUsageAnalyzer(ENTITY_DATA_FILE, GCP_RPC_URL, contract_address)  # Pass contract address
            transactions = analyzer.fetch_transactions_from_rpc(start_block, end_block)
            usage_data = analyzer.analyze_usage_patterns(transactions)
            return usage_data
        except Exception as e:
            return {"error": str(e)}

    fetch_and_cache_data(data_key, _fetch_usage_data, start_block, end_block, pyusd_contract_address)

    with cache_lock:
        cached_data = data_cache.get(data_key)
    if cached_data:
        return jsonify(cached_data["data"]), 200
    else:
        return jsonify({"message": "Analysis in progress. Please try again later."}), 202

@main.route('/usage-analysis')
def usage_analysis():
    """
    Endpoint for analyzing PYUSD usage patterns.  Returns rendered template.
    """
    timeframe = request.args.get('timeframe', '10m')  # Default timeframe
    # # Get all timeframe values
    # timeframe_values = request.args.getlist('timeframe')
    # # Filter out empty values and take the first valid one 
    # timeframe = next((value for value in timeframe_values if value), '10m')
    pyusd_contract_address = current_app.config['PYUSD_CONTRACT_ADDRESS']

    start_block, end_block = get_block_range_from_timeframe(timeframe)
    if not start_block or not end_block:
        error = "Invalid timeframe. Use 'yesterday', 'today', or 'last_week', or 'Xh', 'Xd', 'Xm'"
        return render_template('usage_analysis_dashboard.html', title="PYUSD Usage Analysis", results={}, error=error, start_block=None, end_block=None, timeframe=timeframe), 500

    data_key = f"usage_analysis_{timeframe}_{start_block}_{end_block}_{pyusd_contract_address}"
    def _fetch_usage_data(start_block, end_block, contract_address):
        try:
            analyzer = PYUSDUsageAnalyzer(ENTITY_DATA_FILE, GCP_RPC_URL, contract_address)  # Pass contract address
            transactions = analyzer.fetch_transactions_from_rpc_1(start_block, end_block)
            usage_data = analyzer.analyze_usage_patterns(transactions)
            return usage_data
        except Exception as e:
            return {"error": str(e)}

    results = fetch_and_cache_data(data_key, _fetch_usage_data, start_block, end_block, pyusd_contract_address) #changed
    print(f"results:{results}")

    return render_template('usage_analysis_dashboard.html', title="PYUSD Usage Analysis",
                           results=results, error=None, start_block=start_block, end_block=end_block, timeframe=timeframe)





# --- Congestion Analysis Route ---
@main.route('/congestion-analysis')
def congestion_analysis():
    """Congestion analysis page (showing latest block analysis)."""
    results = None
    error = None
    try:
        analyzer = CongestionAnalyzer(current_app.config)
        latest_block_num = analyzer.get_latest_block_number()
        if latest_block_num:
            block_details = analyzer.get_block_details(latest_block_num)
            if block_details:
                results = analyzer.analyze_block_congestion(block_details)
            else:
                error = f"Could not retrieve details for latest block {latest_block_num}."
        else:
            error = "Could not retrieve latest block number."

    except ConnectionError as e:
         error = f"Could not connect to RPC: {e}"
    except Exception as e:
        error = f"An unexpected error occurred during congestion analysis: {e}"

    return render_template('congestion_analysis_dashboard.html',
                           title="Congestion Analysis",
                           results=results,
                           error=error)


# --- Safe Period Analysis Route ---
@main.route('/safe-period-analysis')
def safe_period_analysis():
    """Safe period analysis page."""
    results = None
    error = None
    # Note: SafePeriodAnalyzer manages its own block history state internally.
   
    try:
        # Creating a new instance each time might be inefficient if block fetching is slow.
        
        analyzer = SafePeriodAnalyzer(current_app.config)
        results = analyzer.assess_safe_period()
        
        if not 'timestamp' in results:
            results['timestamp'] = datetime.now().strftime('%b %d, %Y at %H:%M')
    except ConnectionError as e:
        error = f"Could not connect to RPC: {e}"
    except Exception as e:
        error = f"An unexpected error occurred during safe period analysis: {e}"
    
    return render_template('safe_period_analysis_dashboard.html',
                          title="Safe Period Analysis",
                          results=results,
                          error=error)

# ---  API endpoint for dynamic data ---
@main.route('/api/congestion/latest')
def api_congestion_latest():
     """API endpoint to get latest congestion data."""
     # Similar logic to congestion_analysis route, but returns JSON
     try:
        analyzer = CongestionAnalyzer(current_app.config)
        latest_block_num = analyzer.get_latest_block_number()
        if latest_block_num:
            block_details = analyzer.get_block_details(latest_block_num)
            if block_details:
                results = analyzer.analyze_block_congestion(block_details)
                return jsonify(results)
            else:
                return jsonify({"error": f"Could not retrieve details for block {latest_block_num}"}), 500
        else:
            return jsonify({"error": "Could not retrieve latest block number."}), 500
     except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500


# app/routes.py


@main.route('/token-tracker', methods=['GET', 'POST'])
def token_tracker():
    """
    Handles the input form and displays trace results for the Token Lifetime Tracker.
    """
    # Default values for the form
    default_token = current_app.config.get('PYUSD_CONTRACT_ADDRESS', '')
    default_depth = current_app.config.get('DEFAULT_TRACE_DEPTH', 5)
    max_allowed_depth = current_app.config.get('MAX_TRACE_DEPTH', 20)

    if request.method == 'POST':
        token_address = request.form.get('token_address', '').strip()
        target_address = request.form.get('target_address', '').strip()
        try:
            # Ensure depth is within limits
            max_depth_req = int(request.form.get('max_depth', default_depth))
            max_depth = min(max(1, max_depth_req), max_allowed_depth) # Clamp between 1 and MAX_TRACE_DEPTH
        except (ValueError, TypeError):
            max_depth = default_depth

        error = None
        # --- Input Validation ---
        if not token_address:
             error = "Token Contract Address is required."
        elif not Web3.is_address(token_address):
             error = f"Invalid Token Contract Address format: {token_address}"

        if not target_address and not error:
             error = "Target Address is required."
        elif not Web3.is_address(target_address) and not error:
             error = f"Invalid Target Address format: {target_address}"

        if error:
            flash(error, 'error')
            # Render input form again with error and submitted values
            return render_template(
                'tracker_input.html',
                title="Token Lifetime Tracker",
                token_address=token_address,
                target_address=target_address,
                max_depth=max_depth,
                max_allowed_depth=max_allowed_depth,
                config=current_app.config # Pass config if template needs it
            )

        # --- Call the Service ---
        try:
            # Instantiate the service (consider using application context or DI for larger apps)
            tracer_service = TokenTraceService(current_app.config)
            # Call the main tracing method
            trace_results, trace_error = tracer_service.trace_token_backward(
                token_address_str=token_address,
                target_address_str=target_address,
                max_depth=max_depth
            )

            if trace_error:
                flash(f"Trace Error: {trace_error}", 'error')
                # Show input form again, pre-filled
                return render_template(
                    'tracker_input.html',
                     title="Token Lifetime Tracker",
                     token_address=token_address,
                     target_address=target_address,
                     max_depth=max_depth,
                     max_allowed_depth=max_allowed_depth,
                     config=current_app.config
                 )

            # --- Render Results ---
            # Successfully got results (or empty list if no path found)
            return render_template(
                'trace_results.html',
                title="Trace Results",
                results=trace_results, # This is the list of trace steps
                token_address=token_address,
                target_address=target_address,
                max_depth=max_depth,
                config=current_app.config # Pass config if template needs it
            )

        except ConnectionError as e:
             flash(f"RPC Connection Error: {e}", 'error')
        except Exception as e:
            import traceback
            logger.error(f"Unexpected error in route: {e}\n{traceback.format_exc()}")
            flash(f"An unexpected application error occurred.", 'error') # Don't expose raw error to user

        # Fallback: Render input form if error occurred during service call
        return render_template(
             'tracker_input.html',
              title="Token Lifetime Tracker",
              token_address=token_address,
              target_address=target_address,
              max_depth=max_depth,
              max_allowed_depth=max_allowed_depth,
              config=current_app.config
          )

    # --- GET Request ---
    # Display the initial input form
    return render_template(
        'tracker_input.html',
        title="Token Lifetime Tracker",
        token_address=default_token,
        max_depth=default_depth,
        max_allowed_depth=max_allowed_depth,
        config=current_app.config # Pass config if template needs it
    )

