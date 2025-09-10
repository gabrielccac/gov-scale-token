#!/usr/bin/env python3
import redis
import json
import sys
import concurrent.futures
import threading

# Global Redis client
redis_client = redis.Redis(
    host="redis-14905.crce196.sa-east-1-2.ec2.redns.redis-cloud.com",
    port=14905,
    username="default", 
    password="B9GH59pB85PEQRU5PHmpN4ZSu1hulTgf",
    decode_responses=True
)

lock = threading.Lock()

def get_one_token():
    """Get one token from Redis"""
    with lock:  # Prevent race conditions
        try:
            # Get newest token from sorted set
            result = redis_client.zpopmax("rest_token_sorted_set")
            if not result:
                return None
                
            token_key, _ = result[0]
            
            # Get token data
            token_data_str = redis_client.get(token_key)
            if token_data_str:
                token_data = json.loads(token_data_str)
                redis_client.delete(token_key)  # Cleanup
                return token_data['token']
        except:
            pass
    return None

def get_tokens_concurrent(count=1):
    """Get multiple tokens concurrently"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 10)) as executor:
        futures = [executor.submit(get_one_token) for _ in range(count)]
        tokens = []
        
        for future in concurrent.futures.as_completed(futures):
            token = future.result()
            if token:
                tokens.append(token)
        
        return tokens

if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    tokens = get_tokens_concurrent(count)
    
    for i, token in enumerate(tokens, 1):
        print(f"Token {i}: {token}")
    
    print(f"Got {len(tokens)} tokens")