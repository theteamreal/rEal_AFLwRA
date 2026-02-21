import torch
import torch.nn as nn
import numpy as np

class UniversalMLP(nn.Module):
    """
    A robust, standard architecture for the Antigravity Unified model.
    Designed for tabular data (e.g. CSV features).
    """
    def __init__(self, input_dim: int = 10, out_dim: int = 1):
        super(UniversalMLP, self).__init__()
        self.input_dim = input_dim
        self.out_dim = out_dim
        
        self.model = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, out_dim)
        )

    def forward(self, x):
        return self.model(x)

def create_unified_model(input_dim=10, out_dim=1):
    """Factory function to build the unified global model."""
    return UniversalMLP(input_dim=input_dim, out_dim=out_dim)

def get_state_dict_serializable(model):
    """Converts state_dict to a JSON-serializable format (list of floats)."""
    return {k: v.cpu().numpy().tolist() for k, v in model.state_dict().items()}

def load_state_dict_from_json(model, weights_dict):
    """Loads weights from a JSON-serializable dict back into the model."""
    state_dict = {k: torch.tensor(v, dtype=torch.float32) for k, v in weights_dict.items()}
    model.load_state_dict(state_dict)
