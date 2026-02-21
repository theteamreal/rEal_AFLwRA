import requests
import json
"""
Fedora v2.2 Architecture Verification
-------------------------------------
End-to-end verification of the unified model environment and authentication logic.
"""

BASE_URL = "http://localhost:8000/api"

def verify_unified():
    print("--- ANTIGRAVITY UNIFIED VERIFICATION ---")
    
    # 1. Health
    r = requests.get(f"{BASE_URL}/health")
    print(f"Health: {r.json()}")
    
    # 2. Fetch Model (Unified)
    r = requests.get(f"{BASE_URL}/model")
    model = r.json()
    print(f"Model Version: v{model['version']}")
    print(f"Architecture: {model['input_shape']} -> {model['num_classes']}")
    
    # 3. Submit Update
    # model.0.weight shape: [128, 20], model.2.weight: [64, 128], model.4.weight: [1, 64]
    weights = {
        "model.0.weight": [[0.01] * 20 for _ in range(128)],
        "model.0.bias":   [0.01] * 128,
        "model.2.weight": [[0.01] * 128 for _ in range(64)],
        "model.2.bias":   [0.01] * 64,
        "model.4.weight": [[0.01] * 64 for _ in range(1)],
        "model.4.bias":   [0.01] * 1
    }
    
    print("\nSubmitting participant update...")
    r = requests.post(f"{BASE_URL}/submit-update", json={
        "client_id": "test_unified_node",
        "weights": weights
    })
    print(f"Submission: {r.json()}")

if __name__ == "__main__":
    verify_unified()
