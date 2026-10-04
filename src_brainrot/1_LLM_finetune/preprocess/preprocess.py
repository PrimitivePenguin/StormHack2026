
import pandas as pd
from pathlib import Path

splits = {'train': 'train.jsonl', 'validation': 'validation.jsonl', 'test': 'test.jsonl'}
df = pd.read_json("hf://datasets/ethan00alphayehah/brainrot-dataset/" + splits["train"], lines=True)

# Download database

# Take train database and split it into validation and test sets
def split_dataset(df, train_frac=0.8, val_frac=0.1, test_frac=0.1):
    assert train_frac + val_frac + test_frac == 1.0, "Fractions must sum to 1"

    
    train_size = int(len(df) * train_frac)
    val_size = int(len(df) * val_frac)
    
    train_df = df[:train_size]
    val_df = df[train_size:train_size + val_size]
    test_df = df[train_size + val_size:]
    
    return train_df, val_df, test_df

# 