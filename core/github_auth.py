import time
import webbrowser
import requests
import click
import os
import secrets
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
import threading


class GitHubOAuthFlow:
    """Handle GitHub OAuth web flow authentication"""
    
    # OAuth configuration
    CLIENT_ID = os.environ.get("CE_GITHUB_CLIENT_ID", "")
    CLIENT_SECRET = os.environ.get("CE_GITHUB_CLIENT_SECRET", "")
    CALLBACK_PORT = 8745
    CALLBACK_URL = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"
    
    def __init__(self):
        self.auth_code = None
        self.error = None
        self.state = None
        
    def authenticate(self) -> Optional[str]:
        """Perform OAuth web flow authentication and return access token"""
        
        if not self.CLIENT_ID or not self.CLIENT_SECRET:
            click.echo("\n❌ GitHub OAuth is not configured.", err=True)
            click.echo("\nTo use OAuth authentication, you need to:", err=True)
            click.echo("1. Create a GitHub OAuth App at: https://github.com/settings/applications/new", err=True)
            click.echo("   - Application name: CE Library Wizard", err=True)
            click.echo("   - Homepage URL: https://github.com/your-username/ce-lib-wizard", err=True)
            click.echo(f"   - Authorization callback URL: {self.CALLBACK_URL}", err=True)
            click.echo("2. Set the environment variables:", err=True)
            click.echo("   export CE_GITHUB_CLIENT_ID=your_client_id", err=True)
            click.echo("   export CE_GITHUB_CLIENT_SECRET=your_client_secret", err=True)
            click.echo("\nAlternatively, use a Personal Access Token:", err=True)
            click.echo("   export GITHUB_TOKEN=your_token", err=True)
            return None
        
        # Generate state for CSRF protection
        self.state = secrets.token_urlsafe(32)
        
        # Step 1: Start local HTTP server
        click.echo("\n🔐 Starting OAuth authentication...")
        server = self._start_callback_server()
        
        # Step 2: Open browser for authorization
        auth_params = {
            "client_id": self.CLIENT_ID,
            "redirect_uri": self.CALLBACK_URL,
            "scope": "repo",
            "state": self.state
        }
        auth_url = f"{self.AUTHORIZE_URL}?{urllib.parse.urlencode(auth_params)}"
        
        click.echo(f"📋 Opening browser for authentication...")
        click.echo(f"   If browser doesn't open, visit: {auth_url}")
        
        try:
            webbrowser.open(auth_url)
        except:
            pass
        
        # Step 3: Wait for callback
        click.echo("⏳ Waiting for authentication callback...")
        
        # Wait up to 5 minutes for auth
        timeout = 300
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.auth_code or self.error:
                break
            time.sleep(0.5)
        
        # Shutdown server
        server.shutdown()
        
        if self.error:
            click.echo(f"\n❌ Authentication failed: {self.error}", err=True)
            return None
        
        if not self.auth_code:
            click.echo("\n❌ Authentication timed out", err=True)
            return None
        
        # Step 4: Exchange code for token
        token_data = {
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "code": self.auth_code,
            "redirect_uri": self.CALLBACK_URL
        }
        
        response = requests.post(
            self.TOKEN_URL,
            headers={"Accept": "application/json"},
            data=token_data
        )
        
        if response.status_code != 200:
            click.echo(f"\n❌ Failed to get access token: {response.text}", err=True)
            return None
        
        token_response = response.json()
        if "access_token" in token_response:
            click.echo("\n✅ Authentication successful!")
            return token_response["access_token"]
        else:
            click.echo(f"\n❌ Failed to get access token: {token_response}", err=True)
            return None
    
    def _start_callback_server(self):
        """Start HTTP server to handle OAuth callback"""
        
        class CallbackHandler(BaseHTTPRequestHandler):
            oauth_flow = self
            
            def do_GET(self):
                # Parse the URL
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(self.path)
                
                if parsed.path == "/callback":
                    # Extract parameters
                    params = parse_qs(parsed.query)
                    
                    # Check state for CSRF protection
                    state = params.get("state", [None])[0]
                    if state != self.oauth_flow.state:
                        self.oauth_flow.error = "Invalid state parameter"
                        self._send_error_response()
                        return
                    
                    # Get authorization code
                    code = params.get("code", [None])[0]
                    error = params.get("error", [None])[0]
                    
                    if error:
                        self.oauth_flow.error = error
                        self._send_error_response()
                    elif code:
                        self.oauth_flow.auth_code = code
                        self._send_success_response()
                    else:
                        self.oauth_flow.error = "No code received"
                        self._send_error_response()
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def _send_success_response(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = """
                <html>
                <head><title>Authentication Successful</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>✅ Authentication Successful!</h1>
                    <p>You can now close this window and return to the terminal.</p>
                    <script>window.close();</script>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
            
            def _send_error_response(self):
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                html = f"""
                <html>
                <head><title>Authentication Failed</title></head>
                <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                    <h1>❌ Authentication Failed</h1>
                    <p>Error: {self.oauth_flow.error}</p>
                    <p>Please return to the terminal and try again.</p>
                </body>
                </html>
                """
                self.wfile.write(html.encode())
            
            def log_message(self, format, *args):
                # Suppress log messages
                pass
        
        # Create and start server in a separate thread
        server = HTTPServer(("127.0.0.1", self.CALLBACK_PORT), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
        
        return server


def get_github_token_via_gh_cli() -> Optional[str]:
    """Try to get token from GitHub CLI if installed"""
    try:
        import subprocess
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except:
        pass
    return None


def get_github_token_via_oauth() -> Optional[str]:
    """Get GitHub token using OAuth web flow or gh CLI"""
    # First try GitHub CLI if available
    gh_token = get_github_token_via_gh_cli()
    if gh_token:
        click.echo("✅ Using GitHub CLI authentication")
        return gh_token
    
    # Fall back to OAuth web flow
    auth = GitHubOAuthFlow()
    return auth.authenticate()