# # app/services/__init__.py
# # This file makes the 'services' directory a Python package.
# # You can optionally import service classes here for easier access, e.g.:
# # from .static_analysis_service import SmartContractAnalyzer
# # from .usage_analysis_service import PYUSDUsageAnalyzer
# # etc. Blah Blah Blah
# # app/__init__.py
# from flask import Flask
# from .config import config # Import the config dictionary
# # Import your custom filters
# from .filters import timestamp_to_datetime, format_number
# from .filters import register_filters
# register_filters(app)

# def create_app(config_name='default'):
#     """Application factory function."""
#     app = Flask(__name__)
#     app.config.from_object(config[config_name])

#     # Initialize extensions here if needed (e.g., db, login_manager)

    
#     # Register filters
#     app.jinja_env.filters['timestamp_to_datetime'] = timestamp_to_datetime
#     app.jinja_env.filters['format_number'] = format_number

#     # Register blueprints
#     from .routes import main as main_blueprint
#     app.register_blueprint(main_blueprint)

#     # Add other blueprints if you create more

#     print(f"App created with config: {config_name}")
#     print(f"Using RPC URL: {app.config.get('GCP_RPC_URL')}")
#     print(f"Entity data file: {app.config.get('ENTITY_DATA_FILE')}")


#     return app

from flask import Flask
from .config import config  # Import the config dictionary
from .filters import register_filters  # Just import the function

def create_app(config_name='default'):
    """Application factory function."""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Register Jinja2 filters
    register_filters(app)

    # Register blueprints
    from .routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    # Debug info
    print(f"App created with config: {config_name}")
    print(f"Using RPC URL: {app.config.get('GCP_RPC_URL')}")
    print(f"Entity data file: {app.config.get('ENTITY_DATA_FILE')}")

    return app
