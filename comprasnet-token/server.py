#!/usr/bin/env python3
import os
from fastapi import FastAPI, HTTPException
import redis
import json
import threading
import time
import sys
import uvicorn
from pydantic import BaseModel
from typing import Optional
import logging
from concurrent.futures import ThreadPoolExecutor
from selenium.common.exceptions import TimeoutException
from seleniumbase import Driver
from contextlib import asynccontextmanager

# Tell SeleniumBase to handle thread-locking for multi-threaded runs
sys.argv.append("-n")

# ------------------------------
# Data models
# ------------------------------
class TokenGenerationRequest(BaseModel):
    workers: Optional[int] = 3

class TokenGenerationResponse(BaseModel):
    status: str
    message: str
    workers: int
    queue_size: int

# ------------------------------
# Token Manager
# ------------------------------
class RestTokenManager:
    DEFAULT_TOKEN_EXPIRY = 120  # seconds
    BROWSER_RESTART_THRESHOLD = 2.0
    SCRIPT_TIMEOUT = 10
    CLEANUP_FREQUENCY = 30

    def __init__(self,
                 redis_host,
                 redis_port,
                 redis_username,
                 redis_password,
                 redis_db=0):
        self.max_workers = 3
        self.workers_running = 0
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.worker_shutdown_events = []
        self.generation_active = False
        self.lock = threading.Lock()
        self.token_sorted_set_key = "rest_token_sorted_set"
        self.token_expiry = self.DEFAULT_TOKEN_EXPIRY
        self.url = 'https://cnetmobile.estaleiro.serpro.gov.br/comprasnet-web/public/compras'

        # Redis Cloud connection with username/password
        self.redis_pool = redis.ConnectionPool(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            username=redis_username,
            password=redis_password,
            decode_responses=True,
            max_connections=10
        )
        self.redis_client = redis.Redis(connection_pool=self.redis_pool)

        # Test connection
        try:
            self.redis_client.ping()
            print(f"✅ Connected to Redis Cloud at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            print("❌ Could not connect to Redis Cloud:", e)
            raise
            
        # Start background cleanup thread
        self.cleanup_active = True
        self.cleanup_thread = threading.Thread(target=self._background_cleanup_worker, daemon=True)
        self.cleanup_thread.start()
        print("🧹 Background cleanup thread started")

    # ------------------------------
    # Token Storage (Sorted Set + TTL)
    # ------------------------------
    def get_token_count(self):
        """Get number of available tokens"""
        try:
            return self.redis_client.zcard(self.token_sorted_set_key)
        except Exception as e:
            print(f"Error getting token count: {e}")
            return 0

    def add_token(self, token_data):
        """Add token to sorted set with timestamp as score + individual TTL"""
        timestamp = token_data['timestamp']
        token_key = f"rest_token:{token_data['token'][-10:]}"
        
        # Store token data with TTL
        self.redis_client.setex(token_key, self.token_expiry, json.dumps(token_data))
        
        # Add to sorted set with timestamp as score (newest = highest score)
        self.redis_client.zadd(self.token_sorted_set_key, {token_key: timestamp})
        
        print(f"[REST] Token added (expires in {self.token_expiry}s)")

    def get_newest_token(self):
        """Get newest token (highest score) and remove from sorted set"""
        try:
            # Get token with highest score (newest)
            result = self.redis_client.zpopmax(self.token_sorted_set_key)
            if not result:
                return None
                
            token_key, score = result[0]
            
            # Get token data
            token_data_str = self.redis_client.get(token_key)
            if not token_data_str:
                # Token expired, already cleaned up by Redis
                return None
                
            token_data = json.loads(token_data_str)
            
            # Delete the token data since it's consumed
            self.redis_client.delete(token_key)
            
            return token_data
            
        except Exception as e:
            print(f"Error getting newest token: {e}")
            return None

    def cleanup_stale_references(self):
        """Manual cleanup of stale token references"""
        try:
            current_time = time.time()
            expired_cutoff = current_time - self.token_expiry - 60  # 60s buffer
            
            print(f"🧹 Running cleanup - current_time: {current_time}, cutoff: {expired_cutoff}")
            
            # Remove tokens with timestamps OLDER than cutoff (lower scores)
            removed = self.redis_client.zremrangebyscore(
                self.token_sorted_set_key, 
                "-inf", 
                expired_cutoff
            )
            
            print(f"🧹 Cleaned {removed} stale token references")
            return removed
            
        except Exception as e:
            print(f"🧹 Cleanup error: {e}")
            return 0

    def _background_cleanup_worker(self):
        """Background worker that continuously cleans stale token references"""
        print("🧹 Background cleanup worker started")
        
        while self.cleanup_active:
            try:
                removed = self.cleanup_stale_references()
                
                # Sleep for cleanup frequency (30 seconds for testing)
                print(f"🧹 Sleeping for 30 seconds...")
                time.sleep(30)
                
            except Exception as e:
                print(f"🧹 Background cleanup error: {e}")
                time.sleep(60)  # Wait 1 minute before retrying on error
                
        print("🧹 Background cleanup worker stopped")

    # ------------------------------
    # Worker management
    # ------------------------------
    def start_token_generation(self, workers=None):
        with self.lock:
            if self.generation_active:
                return False, "Token generation already active"
            self.generation_active = True
            self.max_workers = workers or self.max_workers

        print(f"🚀 [REST] Starting {self.max_workers} token generation workers...")
        self.worker_shutdown_events = [threading.Event() for _ in range(self.max_workers)]
        for i in range(self.max_workers):
            self.executor.submit(self.token_worker, i + 1, self.worker_shutdown_events[i])
        return True, f"Started {self.max_workers} workers"

    def stop_token_generation(self):
        with self.lock:
            if not self.generation_active:
                return False, "Token generation not active"
            self.generation_active = False

        print("🛑 [REST] Stopping token generation workers...")
        for event in self.worker_shutdown_events:
            event.set()

        timeout = 10
        start_time = time.time()
        while self.workers_running > 0 and (time.time() - start_time) < timeout:
            time.sleep(0.1)
            
        return True, "Token generation stopped"

    def token_worker(self, worker_id, shutdown_event):
        with self.lock:
            self.workers_running += 1
        print(f"[REST Worker {worker_id}] Started")
        driver = None

        try:
            while not shutdown_event.is_set():
                try:
                    if driver is None:
                        driver = Driver(uc=True, headless=True, no_sandbox=True)
                        driver.get(self.url)
                        driver.set_script_timeout(self.SCRIPT_TIMEOUT)
                        driver.sleep(2)

                    if shutdown_event.is_set():
                        break

                    token, duration = self.generate_token(driver)
                    if token:
                        token_data = {
                            "token": token,
                            "duration": duration,
                            "worker_id": worker_id,
                            "timestamp": time.time(),
                            "source": "rest_api"
                        }
                        self.add_token(token_data)
                        print(f"[REST Worker {worker_id}] Generated token in {duration:.2f}s")
                    else:
                        if driver:
                            driver.quit()
                            driver = None

                    if duration > self.BROWSER_RESTART_THRESHOLD:
                        if driver:
                            driver.quit()
                            driver = None

                except TimeoutException:
                    if driver:
                        driver.quit()
                        driver = None
                except Exception as e:
                    if driver:
                        driver.quit()
                        driver = None
                    time.sleep(1)

        finally:
            with self.lock:
                self.workers_running -= 1
            if driver:
                driver.quit()
            print(f"[REST Worker {worker_id}] Stopped")

    # ------------------------------
    # Token generation JS
    # ------------------------------
    def generate_token(self, driver):
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
            token = driver.execute_script(js_to_get_token)
            duration = time.time() - start_time
            return str(token) if token else None, duration
        except Exception as e:
            duration = time.time() - start_time
            return None, duration

    # ------------------------------
    # Status
    # ------------------------------
    def get_status(self):
        return {
            "generation_active": self.generation_active,
            "workers_running": self.workers_running,
            "max_workers": self.max_workers,
            "token_count": self.get_token_count(),
            "token_expiry": self.token_expiry,
            "storage": "redis_cloud_sorted_set",
            "sorted_set_key": self.token_sorted_set_key,
            "cleanup_thread_alive": self.cleanup_thread.is_alive() if hasattr(self, 'cleanup_thread') else False,
            "cleanup_active": getattr(self, 'cleanup_active', False)
        }

# ------------------------------
# Redis Cloud Configuration
# ------------------------------
REDIS_HOST = os.getenv("REDIS_HOST", "redis-14905.crce196.sa-east-1-2.ec2.redns.redis-cloud.com")
REDIS_PORT = int(os.getenv("REDIS_PORT", "14905"))
REDIS_USER = os.getenv("REDIS_USER", "default")
REDIS_PASS = os.getenv("REDIS_PASS", "B9GH59pB85PEQRU5PHmpN4ZSu1hulTgf")

# Initialize token manager
token_manager = RestTokenManager(
    redis_host=REDIS_HOST,
    redis_port=REDIS_PORT,
    redis_username=REDIS_USER,
    redis_password=REDIS_PASS
)

# ------------------------------
# FastAPI App
# ------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Token Generation REST API Server")
    yield
    print("🛑 Shutting down REST API server...")
    token_manager.stop_token_generation()

app = FastAPI(title="Token Generation REST API (Redis Cloud)", version="1.1.0", lifespan=lifespan)

@app.post("/start", response_model=TokenGenerationResponse)
async def start_token_generation(request: TokenGenerationRequest = TokenGenerationRequest()):
    success, message = token_manager.start_token_generation(request.workers)
    if success:
        return TokenGenerationResponse(
            status="started",
            message=message,
            workers=token_manager.workers_running,
            queue_size=token_manager.get_token_count()
        )
    raise HTTPException(status_code=400, detail=message)

@app.post("/stop", response_model=TokenGenerationResponse)
async def stop_token_generation():
    success, message = token_manager.stop_token_generation()
    if success:
        return TokenGenerationResponse(
            status="stopped",
            message=message,
            workers=token_manager.workers_running,
            queue_size=token_manager.get_token_count()
        )
    raise HTTPException(status_code=400, detail=message)

@app.get("/status")
async def get_token_status():
    return token_manager.get_status()

@app.get("/tokens")
async def get_token_info():
    """Get information about available tokens"""
    token_count = token_manager.get_token_count()
    
    # Sample some tokens from sorted set without removing them
    sample_info = []
    try:
        # Get top 5 newest tokens (highest scores) without removing
        token_keys_with_scores = token_manager.redis_client.zrevrange(
            token_manager.token_sorted_set_key, 0, 4, withscores=True
        )
        
        for token_key, timestamp in token_keys_with_scores:
            token_data_str = token_manager.redis_client.get(token_key)
            if token_data_str:
                try:
                    token_data = json.loads(token_data_str)
                    age = time.time() - timestamp
                    sample_info.append({
                        "token_suffix": token_data['token'][-10:],
                        "age_seconds": round(age, 1),
                        "worker_id": token_data.get("worker_id"),
                        "duration": token_data.get("duration"),
                        "timestamp": timestamp
                    })
                except:
                    pass
        
    except Exception as e:
        print(f"Error sampling tokens: {e}")
    
    return {
        "token_count": token_count,
        "sample_tokens": sample_info,
        "average_age": round(sum(t["age_seconds"] for t in sample_info) / len(sample_info), 1) if sample_info else 0,
        "storage_type": "sorted_set_lifo"
    }

@app.delete("/tokens")
async def clear_tokens():
    """Clear all tokens from storage"""
    cleared = token_manager.redis_client.delete(token_manager.token_sorted_set_key)
    return {"status": "cleared", "message": "Cleared all tokens", "previous_count": cleared}

@app.get("/token")
async def get_newest_token():
    """Get the newest available token"""
    token_data = token_manager.get_newest_token()
    if token_data:
        return {
            "status": "success",
            "token": token_data['token'],
            "duration": token_data['duration'],
            "worker_id": token_data['worker_id'],
            "timestamp": token_data['timestamp'],
            "age_seconds": round(time.time() - token_data['timestamp'], 1)
        }
    else:
        raise HTTPException(status_code=404, detail="No tokens available")

@app.get("/health")
async def health_check():
    try:
        token_manager.redis_client.ping()
        return {
            "status": "healthy",
            "redis": "connected",
            "generation_active": token_manager.generation_active,
            "workers": token_manager.workers_running
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Unhealthy: {e}")

@app.post("/cleanup")
async def cleanup_stale_tokens():
    """Manually trigger cleanup of stale token references"""
    try:
        removed = token_manager.cleanup_stale_references()
        return {
            "status": "success",
            "message": f"Cleaned {removed} stale token references",
            "removed": removed
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {e}")

@app.get("/config")
async def get_config():
    return {
        "token_expiry": token_manager.token_expiry,
        "browser_restart_threshold": token_manager.BROWSER_RESTART_THRESHOLD,
        "cleanup_frequency": token_manager.CLEANUP_FREQUENCY,
        "script_timeout": token_manager.SCRIPT_TIMEOUT,
        "max_workers": token_manager.max_workers,
        "redis_host": REDIS_HOST,
        "redis_port": REDIS_PORT
    }

# ------------------------------
# Run server
# ------------------------------
if __name__ == "__main__":
    print("🚀 Starting Token Generation REST API Server (Redis Cloud)")
    print("📍 API: http://localhost:8000")
    print(f"🔧 Redis Cloud: {REDIS_HOST}:{REDIS_PORT}")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
