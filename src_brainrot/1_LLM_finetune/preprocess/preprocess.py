
import pandas as pd
from pathlib import Path

SOURCE_URL = "hf://datasets/ethan00alphayehah/brainrot-dataset/train.jsonl"
DATA_DIR = Path("data")
SEED = 0                    # same seed = same split for everyone
 
N_TEST_INPUTS = 35          # small on purpose: humans rate these by hand
N_VAL_INPUTS = 150          # enough to watch validation loss
MAX_PER_INPUT = 3           # at most 3 brainrot versions of the same English sentence
CAP_SHARE = 0.05            # at most 5% of rows may contain each overused pattern
CAP_PATTERNS = ["🙏", r"\bking\b", r"\bqueen\b"]   # \b = whole word ("thinking" is safe)

# 1. Load raw
def load_raw() -> pd.DataFrame:
    return pd.read_json(SOURCE_URL, lines=True)

# 2. Clean
def clean(df: pd.DataFrame) -> pd.DataFrame:
    # Trip spaces, remove empty rows drop duplicates
    df = df[["source", "target"]].copy() #keep only source  target
    
    # convert to string  + strip() removes whitespace from beg + end
    df["source"] = df["source"].fillna("").astype(str).str.strip()
    df["target"] = df["target"].fillna("").astype(str).str.strip()

    # Remove row when either column is empty
    df = df[(df["source"] != "") & (df["target"] != "")]

    # Remove dupcliates
    df = df.drop_duplicates(subset=["source", "target"]).reset_index(drop = True)
    return df

# 3. Add pattern recognition
def add_key(df: pd.DataFrame) -> pd.DataFrame:
    # strip punctuation, lowercase, and add a key col for pattern
    df = df.copy()
    df["key"] = (df["source"].str.lower()
                .str.replace(r"[^\w\s]", "", regex=True)
                .str.replace(r"\s+", " ", regex=True)
                .str.strip())
    return df

# 4. Cap repeats
def cap_repeats(df: pd.DataFrame) -> pd.DataFrame:
    shuffled = df.sample(frac=1, random_state=SEED)
    return shuffled.groupby("key", sort=False).head(MAX_PER_INPUT).reset_index(drop=True)

# 5. Cap patterns
def cap_patterns(df: pd.DataFrame) -> pd.DataFrame:
    for pattern in CAP_PATTERNS:
        hits = df[df["target"].str.contains(pattern, case=False, regex=True)]
        limit = int(CAP_SHARE * len(df))
        if len(hits) > limit:
            drop = hits.sample(len(hits) - limit, random_state=SEED).index
            df = df.drop(drop)
    return df.reset_index(drop=True)

# 6. Split dataset
def split(df: pd.DataFrame) -> dict:
    # Split by English sentence
    keys = df["key"].drop_duplicates().sample(frac=1, random_state=SEED).tolist()
    test_keys = set(keys[:N_TEST_INPUTS])
    val_keys = set(keys[N_TEST_INPUTS:N_TEST_INPUTS + N_VAL_INPUTS])

    test = df[df["key"].isin(test_keys)].drop_duplicates("key")   # one row per test input
    val = df[df["key"].isin(val_keys)]
    train = df[~df["key"].isin(test_keys | val_keys)]
    return {"train": train, "val": val, "test": test}


# 7. Save dataset
def save(parts: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, part in parts.items():
        part[["source", "target"]].to_json(
            DATA_DIR / f"{name}.jsonl", orient="records", lines=True, force_ascii=False,
        )
    
# 8. Report
def report(raw: pd.DataFrame, parts: dict) -> None:
    print(f"raw rows: {len(raw)}")
    for name, part in parts.items():
        print(f"{name:>5}: {len(part):5d} rows, {part['key'].nunique():5d} unique inputs")
    train = parts["train"]
    for pattern in CAP_PATTERNS:
        share = train["target"].str.contains(pattern, case=False, regex=True).mean()
        print(f"train rows with {pattern!r}: {share:.1%}")
 


def main() -> None:
    raw = load_raw()
    df = cap_patterns(cap_repeats(add_key(clean(raw))))
    parts = split(df)
    save(parts)
    report(raw, parts)
                                  
if __name__ == "__main__":
    main()