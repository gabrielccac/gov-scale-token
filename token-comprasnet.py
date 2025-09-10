# type: ignore
#!/usr/bin/env python3
import threading
import time
from fastapi import FastAPI, HTTPException
from seleniumbase import Driver
from selenium.common.exceptions import TimeoutException
import uvicorn
from pydantic import BaseModel
from contextlib import asynccontextmanager
import sys

# Tell SeleniumBase to handle thread-locking
sys.argv.append("-n")

class TokenResponse(BaseModel):
    token: str
    duration: float
    timestamp: float

class StatusResponse(BaseModel):
    status: str
    browser_ready: bool
    last_keepalive: float
    uptime: float

class OnDemandTokenServer:
    def __init__(self):
        self.driver = None
        self.browser_ready = False
        self.lock = threading.Lock()
        self.url = 'https://cnetmobile.estaleiro.serpro.gov.br/comprasnet-web/public/compras'
        self.last_keepalive = 0
        self.start_time = time.time()
        self.keepalive_interval = 300  # 5 minutes
        
        # Start browser and keepalive thread
        self._initialize_browser()
        self._start_keepalive_thread()
    
    def _initialize_browser(self):
        """Initialize the browser"""
        print("🚀 Initializing browser...")
        try:
            self.driver = Driver(uc=True, headless=True, no_sandbox=True)
            self.driver.get(self.url)
            self.driver.set_script_timeout(10)
            self.driver.sleep(2)
            
            # Wait for hCaptcha
            while not self.driver.is_element_present('[data-hcaptcha-widget-id]', by="css selector"):
                print("⏳ Waiting for hCaptcha...")
                self.driver.get(self.url)
                self.driver.sleep(2)
            
            self.browser_ready = True
            self.last_keepalive = time.time()
            print("✅ Browser ready!")
            
        except Exception as e:
            print(f"❌ Browser initialization failed: {e}")
            self.browser_ready = False
    
    def _start_keepalive_thread(self):
        """Start background thread for keepalive tokens"""
        def keepalive_worker():
            while True:
                try:
                    time.sleep(30)  # Check every 30 seconds
                    
                    if not self.browser_ready:
                        continue
                    
                    # Generate keepalive token if 5 minutes passed
                    if time.time() - self.last_keepalive >= self.keepalive_interval:
                        print("💓 Generating keepalive token...")
                        with self.lock:
                            try:
                                token, duration = self._generate_token()
                                if token:
                                    print(f"💓 Keepalive token generated in {duration:.2f}s")
                                    self.last_keepalive = time.time()
                                else:
                                    print("💓 Keepalive token failed, refreshing page...")
                                    self.driver.get(self.url)
                                    self.driver.sleep(2)
                            except Exception as e:
                                print(f"💓 Keepalive error: {e}")
                                
                                # Restart browser on any error during keepalive token generation
                                print("🔄 Keepalive error detected - restarting browser...")
                                self.browser_ready = False
                                if self.driver:
                                    try:
                                        self.driver.quit()
                                    except:
                                        pass
                                self._initialize_browser()
                                
                except Exception as e:
                    print(f"Keepalive thread error: {e}")
        
        thread = threading.Thread(target=keepalive_worker, daemon=True)
        thread.start()
    
    def _generate_token(self):
        """Generate a single token (must be called with lock held)"""
        if not self.browser_ready or not self.driver:
            return None, 0
        
        start_time = time.time()
        
        js_to_get_token = """
        return new Promise((resolve) => {
            (async function() {
                const element = document.querySelector('[data-hcaptcha-widget-id]');
                const captchaId = element.getAttribute('data-hcaptcha-widget-id');
                const response = await hcaptcha.execute(captchaId, {async: true});
                resolve(response.response);
            })();
        });
        """
        
        try:
            token = self.driver.execute_script(js_to_get_token)
            duration = time.time() - start_time
            return str(token) if token else None, duration
        except Exception as e:
            duration = time.time() - start_time
            print(f"Token generation error: {e}")
            
            # Restart browser on any error during token generation
            print("🔄 Error detected - restarting browser...")
            self.browser_ready = False
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            self._initialize_browser()
                
            return None, duration
    
    def _refresh_page(self):
        """Refresh the page (must be called with lock held)"""
        try:
            if self.driver:
                self.driver.get(self.url)
                self.driver.sleep(2)
        except Exception as e:
            print(f"Page refresh error: {e}")
    
    def get_token(self):
        """Get a token on demand"""
        if not self.browser_ready:
            raise Exception("Browser not ready")
        
        # Generate new token
        with self.lock:
            token, duration = self._generate_token()
            
            if not token:
                # Try refreshing page and generating again
                print("🔄 Token failed, refreshing page and retrying...")
                self._refresh_page()
                token, duration = self._generate_token()
            
            if not token:
                raise Exception("Failed to generate token after retry")
            
            # Update keepalive timestamp since we generated a token
            self.last_keepalive = time.time()
            
            return {
                "token": token,
                "duration": duration,
                "timestamp": time.time()
            }
    
    def restart_browser(self):
        """Restart the browser"""
        with self.lock:
            print("🔄 Restarting browser...")
            
            # Close existing browser
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
            
            self.browser_ready = False
            self.driver = None
            
            # Initialize new browser
            self._initialize_browser()
            
            # Wait a moment for browser to be fully ready
            if self.browser_ready:
                print("✅ Browser restart completed successfully")
            else:
                print("❌ Browser restart failed")
            
            return self.browser_ready
    
    def get_status(self):
        """Get server status"""
        return {
            "status": "ready" if self.browser_ready else "not_ready",
            "browser_ready": self.browser_ready,
            "last_keepalive": self.last_keepalive,
            "uptime": time.time() - self.start_time
        }
    
    def cleanup(self):
        """Cleanup resources"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass

# Global token server variable
token_server = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global token_server
    token_server = OnDemandTokenServer()
    yield
    # Shutdown
    print("🛑 Shutting down server...")
    if token_server:
        token_server.cleanup()

# FastAPI app
app = FastAPI(title="On-Demand Token Server", version="1.0.0", lifespan=lifespan)

@app.get("/token", response_model=TokenResponse)
async def get_token():
    """Get a token on demand"""
    try:
        result = token_server.get_token()
        return TokenResponse(
            token=result["token"],
            duration=result["duration"],
            timestamp=result["timestamp"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate token: {str(e)}")

@app.post("/restart")
async def restart_browser():
    """Restart the browser"""
    try:
        success = token_server.restart_browser()
        if success:
            return {"status": "restarted", "browser_ready": True}
        else:
            raise HTTPException(status_code=500, detail="Failed to restart browser")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restart failed: {str(e)}")

@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get server status"""
    try:
        status = token_server.get_status()
        return StatusResponse(
            status=status["status"],
            browser_ready=status["browser_ready"],
            last_keepalive=status["last_keepalive"],
            uptime=status["uptime"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


if __name__ == "__main__":
    print("🚀 Starting On-Demand Token Server")
    print("📍 API available at: http://localhost:8002")
    print("📖 Documentation at: http://localhost:8002/docs")
    print()
    print("Available endpoints:")
    print("  GET  /token   - Get a token on demand")
    print("  POST /restart - Restart browser")
    print("  GET  /status  - Get server status")
    print()
    
    try:
        uvicorn.run(
            "token-comprasnet:app",
            host="0.0.0.0", 
            port=8002,
            reload=False,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
        if token_server:
            token_server.cleanup()
    except Exception as e:
        print(f"❌ Server error: {e}")
        if token_server:
            token_server.cleanup()