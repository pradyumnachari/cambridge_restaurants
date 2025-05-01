from typing import Any, List, Dict, Optional
import csv
import os
import httpx
from mcp.server.fastmcp import FastMCP  # Main MCP server class
from starlette.applications import Starlette  # ASGI framework
from starlette.responses import HTMLResponse  # Add HTML response
from mcp.server.sse import SseServerTransport  # SSE transport implementation
from starlette.requests import Request
from starlette.routing import Mount, Route
from mcp.server import Server  # Base server class
import uvicorn  # ASGI server

# Initialize FastMCP server with a name
# This name appears to clients when they connect
mcp = FastMCP("menu")

# Path to the menu CSV file - adjust this if needed
MENU_CSV_PATH = "menu.csv"

# Debug mode for additional logging
DEBUG = True

def debug_log(message: str) -> None:
    """Print debug messages if DEBUG is enabled."""
    if DEBUG:
        print(f"[DEBUG] {message}")

# Cache for menu data to avoid reading the file on every request
_menu_cache: Optional[List[Dict[str, Any]]] = None


def load_menu() -> List[Dict[str, Any]]:
    """Load menu data from CSV file.
    
    Returns:
        List of dictionaries, where each dictionary represents a menu item.
    """
    global _menu_cache
    
    # Return cached data if available
    if _menu_cache is not None:
        return _menu_cache
    
    # Ensure the file exists
    if not os.path.exists(MENU_CSV_PATH):
        raise FileNotFoundError(f"Menu file not found: {MENU_CSV_PATH}")
    
    menu_items = []
    
    # Read CSV file
    with open(MENU_CSV_PATH, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        
        # Validate that required columns exist
        fieldnames = reader.fieldnames
        if not fieldnames or 'Item' not in fieldnames:
            raise ValueError(f"CSV file missing required 'Item' column. Available columns: {fieldnames}")
        
        for row in reader:
            # Convert numeric fields to appropriate types
            if 'Price_USD' in row and row['Price_USD']:
                try:
                    row['Price_USD'] = float(row['Price_USD'])
                except ValueError:
                    # If conversion fails, keep as string
                    pass
                    
            menu_items.append(row)
    
    # Cache the data
    _menu_cache = menu_items
    return menu_items


def refresh_menu_cache() -> None:
    """Force a refresh of the menu cache.
    
    Call this when you know the menu file has changed.
    """
    global _menu_cache
    _menu_cache = None


# Define a tool using the @mcp.tool() decorator
@mcp.tool()
async def get_items() -> str:
    """Get a list of all item names in the menu.
    
    Returns:
        A formatted string listing all item names in the menu.
    """
    try:
        debug_log("Loading menu data")
        menu = load_menu()
        
        if not menu:
            return "The menu is empty."
        
        debug_log(f"Loaded {len(menu)} items")
        
        # Extract all item names with error handling for each item
        item_names = []
        for i, item in enumerate(menu):
            try:
                if 'Item' not in item:
                    debug_log(f"Item {i} missing 'Item' field. Available keys: {list(item.keys())}")
                    continue
                    
                item_names.append(item['Item'])
            except Exception as e:
                debug_log(f"Error processing item {i}: {str(e)}")
        
        debug_log(f"Found {len(item_names)} valid item names")
        
        # Format the result
        result = "Available items on menu:\n\n"
        for i, name in enumerate(item_names, 1):
            result += f"{i}. {name}\n"
        
        return result
    
    except FileNotFoundError as e:
        error_msg = f"Error: {str(e)}"
        debug_log(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"An error occurred while retrieving menu items: {str(e)}"
        debug_log(error_msg)
        return error_msg


@mcp.tool()
async def get_item_info(item_name: str) -> str:
    """Get detailed information about a specific item on the menu.
    
    Args:
        item_name: The name of the item to look up
        
    Returns:
        A formatted string containing all information about the specified item,
        or an error message if the item is not found.
    """
    try:
        menu = load_menu()
        
        # Find the item in the menu
        item = None
        for menu_item in menu:
            if menu_item['Item'].lower() == item_name.lower():
                item = menu_item
                break
        
        # If exact match not found, try partial matching
        if item is None:
            for menu_item in menu:
                if item_name.lower() in menu_item['Item'].lower():
                    item = menu_item
                    break
        
        if item is None:
            return f"Item '{item_name}' not found on the menu."
        
        # Format the item information
        result = f"Information for: {item['Item']}\n\n"
        
        for key, value in item.items():
            # Skip Item since it's already in the header
            if key != 'Item':
                # Format the key for better readability
                formatted_key = ' '.join(word.capitalize() for word in key.split('_'))
                result += f"{formatted_key}: {value}\n"
        
        return result
    
    except FileNotFoundError as e:
        return f"Error: {str(e)}"
    except Exception as e:
        return f"An error occurred while retrieving item information: {str(e)}"


# Add a homepage handler for root URL
async def homepage(request: Request) -> HTMLResponse:
    """Handle requests to the root URL by returning a simple HTML page."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCP Menu Server</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 20px;
                line-height: 1.6;
            }
            h1 {
                color: #333;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
            }
            .status {
                padding: 10px;
                background-color: #e6f7e6;
                border-left: 4px solid #28a745;
                margin-bottom: 20px;
            }
            button {
                padding: 8px 16px;
                background-color: #007bff;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            button:hover {
                background-color: #0069d9;
            }
            #status-box {
                margin-top: 20px;
                padding: 10px;
                border: 1px solid #ddd;
                min-height: 100px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>MCP Menu Server</h1>
            <div class="status">Server is running correctly!</div>
            
            <button id="connect-btn">Connect to SSE</button>
            
            <div id="status-box">Connection status will appear here...</div>
            
            <h2>Available Tools:</h2>
            <ul>
                <li><strong>get_items</strong> - Get a list of all items on the menu</li>
                <li><strong>get_item_info</strong> - Get detailed information about a specific item</li>
            </ul>
            
            <script>
                document.getElementById('connect-btn').addEventListener('click', function() {
                    const statusBox = document.getElementById('status-box');
                    statusBox.innerHTML = 'Connecting to SSE...';
                    
                    try {
                        const eventSource = new EventSource('/sse');
                        
                        eventSource.onopen = function() {
                            statusBox.innerHTML += '<br>Connection established!';
                        };
                        
                        eventSource.onerror = function(error) {
                            statusBox.innerHTML += '<br>Error: Connection failed';
                            eventSource.close();
                        };
                        
                        eventSource.addEventListener('message', function(event) {
                            statusBox.innerHTML += `<br>Received: ${event.data}`;
                        });
                    } catch (error) {
                        statusBox.innerHTML += `<br>Error: ${error.message}`;
                    }
                });
            </script>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# Create a Starlette application with SSE transport
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided mcp server with SSE.
    
    This sets up the HTTP routes and SSE connection handling.
    """
    # Create an SSE transport with a path for messages
    sse = SseServerTransport("/messages/")

    # Handler for SSE connections
    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,  # access private method
        ) as (read_stream, write_stream):
            # Run the MCP server with the SSE streams
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    # Create and return the Starlette application
    return Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=homepage),  # Add root URL handler
            Route("/sse", endpoint=handle_sse),  # Endpoint for SSE connections
            Mount("/messages/", app=sse.handle_post_message),  # Endpoint for messages
        ],
    )


if __name__ == "__main__":
    # Get the underlying MCP server from FastMCP wrapper
    mcp_server = mcp._mcp_server

    import argparse
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Run Menu MCP Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8080, help='Port to listen on')
    args = parser.parse_args()

    print(f"Starting Menu MCP Server on {args.host}:{args.port}")
    print(f"Menu file: {MENU_CSV_PATH}")
    
    try:
        # Test loading the menu to catch errors early
        menu_count = len(load_menu())
        print(f"Successfully loaded {menu_count} menu items")
    except Exception as e:
        print(f"Error loading menu: {e}")
        print("Server will still start, but tools may not work correctly")

    # Create and run the Starlette application
    starlette_app = create_starlette_app(mcp_server, debug=True)
    uvicorn.run(starlette_app, host=args.host, port=args.port)