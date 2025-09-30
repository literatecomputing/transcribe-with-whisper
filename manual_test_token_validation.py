#!/usr/bin/env python3
"""
Test script for HuggingFace token validation scenarios.
This helps test model access validation without needing to "un-accept" models.
"""

import requests
import json

# Test different token scenarios
test_scenarios = [
    {
        "name": "Empty token",
        "token": "",
        "expected": "Token is empty"
    },
    {
        "name": "Invalid format",
        "token": "invalid_token_format",
        "expected": "Invalid token format"
    },
    {
        "name": "Fake token (proper format)",
        "token": "hf_1234567890abcdefghijklmnopqrstuvwxyz",
        "expected": "Invalid token or API access denied"
    },
    {
        "name": "Real token format but non-existent",
        "token": "hf_AbCdEfGhIjKlMnOpQrStUvWxYz1234567890",
        "expected": "Invalid token or API access denied"
    },
    {
        "name": "Simulated no model access (test scenario)",
        "token": "hf_test_no_access_1234567890abcdefghijklm",
        "expected": "License acceptance required",
        "test_special": True
    }
]

def test_token_validation(base_url="http://localhost:5001"):
    """Test token validation with different scenarios"""
    print("🧪 Testing Token Validation Scenarios")
    print("=" * 50)
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{i}. Testing: {scenario['name']}")
        print(f"   Token: {scenario['token'][:20]}{'...' if len(scenario['token']) > 20 else ''}")
        
        try:
            payload = {"token": scenario["token"]}
            if scenario.get("test_special"):
                # This will trigger the special test scenario in the server
                pass
                
            response = requests.post(
                f"{base_url}/api/test-token",
                json=payload,
                timeout=10
            )
            
            result = response.json()
            
            success_expected = scenario["expected"] in ["Token validated successfully", "✅"]
            actual_success = result.get('success', False)
            
            if success_expected == actual_success:
                print(f"   Status: ✅ PASS")
            else:
                print(f"   Status: ❌ FAIL (expected success={success_expected}, got={actual_success})")
            
            print(f"   Error: {result.get('error', 'No error')}")
            
            if result.get('requires_license_acceptance'):
                print("   🔒 Requires license acceptance")
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ REQUEST FAILED: {e}")
        except Exception as e:
            print(f"   ❌ ERROR: {e}")

def test_with_real_token(token, base_url="http://localhost:5001"):
    """Test with a real token to see detailed model access info"""
    print(f"\n🔍 Testing Real Token")
    print("=" * 30)
    
    try:
        response = requests.post(
            f"{base_url}/api/test-token",
            json={"token": token},
            timeout=15
        )
        
        result = response.json()
        
        print(f"Valid: {'✅ YES' if result['success'] else '❌ NO'}")
        if result.get('message'):
            print(f"Message: {result['message']}")
        if result.get('error'):
            print(f"Error: {result['error']}")
        if result.get('requires_license_acceptance'):
            print("🔒 License acceptance required")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

def check_server_status(base_url="http://localhost:5001"):
    """Check if the server is running"""
    try:
        response = requests.get(f"{base_url}/api/check-token", timeout=5)
        print("✅ Server is running")
        return True
    except:
        print(f"❌ Server not reachable at {base_url}")
        return False

if __name__ == "__main__":
    print("🚀 HuggingFace Token Validation Tester")
    print("=" * 50)
    
    # Check if server is running
    if not check_server_status():
        print("\n💡 Start the server first:")
        print("   python3 transcribe_with_whisper/web_server.py")
        exit(1)
    
    # Run invalid token tests
    test_token_validation()
    
    # Test with real token if provided
    import os
    real_token = os.getenv("HUGGING_FACE_AUTH_TOKEN")
    if real_token:
        test_with_real_token(real_token)
    else:
        print(f"\n💡 To test with your real token:")
        print(f"   export HUGGING_FACE_AUTH_TOKEN=your_token_here")
        print(f"   python3 {__file__}")
    
    print(f"\n🌐 You can also test manually at:")
    print(f"   http://localhost:5001/setup")
