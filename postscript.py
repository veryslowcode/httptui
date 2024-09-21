import os
import sys

# Access the request object through sys.argv
response = sys.argv[1]

# Set environment variable for use in application
os.environ["json_path"] = f"/response/{response.status_code}"
