# run.py
import os
from app import create_app

# Load environment variables if using a .env file (optional)
# from dotenv import load_dotenv
# load_dotenv()

config_name = os.getenv('FLASK_CONFIG') or 'default'
app = create_app(config_name)

if __name__ == '__main__':
    # Use host='0.0.0.0' to make it accessible on your network
    app.run(host='0.0.0.0', port=5001)