#!/usr/bin/env python3
"""
Prepare NLP training data from ACUHIT 2 parquet files.
Maps ICD-10 codes → severity labels automatically.

Usage:
    python scripts/prepare_nlp_data.py
"""

import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split

# ── Paths ───────────────────────────────────────────────────
CACHE_DIR = Path(__file__).parent.parent / ".cache"
OUTPUT_DIR = Path(__file__).parent.parent / "nlp_data"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── ICD-10 to Severity Mapping ─────────────────────────────
# First character of ICD-10 code → severity score
ICD_SEVERITY = {
    # Critical (life-threatening)
    "I": -1.0,  # Circulatory (heart attack, stroke)
    "C": -1.0,  # Cancer
    "J44": -0.9,  # COPD
    "J45": -0.9,  # Asthma severe
    "N17": -0.9,  # Renal failure
    "N18": -0.9,  # Chronic kidney disease
    
    # Severe
    "J": -0.7,  # Respiratory (pneumonia, bronchitis)
    "K": -0.6,  # Digestive (ulcers, liver disease)
    "G": -0.6,  # Neurological
    
    # Moderate
    "E": -0.4,  # Endocrine (diabetes, thyroid)
    "M": -0.3,  # Musculoskeletal (arthritis, back pain)
    "L": -0.3,  # Skin conditions
    
    # Mild
    "R": -0.1,  # Symptoms (fever, pain, cough)
    "F": -0.2,  # Mental health (anxiety, depression)
    "H": -0.1,  # Eye/ear conditions
    
    # Stable/Healthy
    "Z": 0.5,   # Check-ups, screenings, healthy encounters
}

def get_severity_from_icd(icd_code: str) -> float:
    """
    Map ICD-10 code to severity score.
    Returns float: -1.0 (critical) to +0.5 (stable)
    """
    if not icd_code or not isinstance(icd_code, str):
        return 0.0  # Unknown → neutral
    
    icd_upper = icd_code.strip().upper()
    
    # Try 3-character code first (more specific)
    if len(icd_upper) >= 3:
        three_char = icd_upper[:3]
        if three_char in ICD_SEVERITY:
            return ICD_SEVERITY[three_char]
    
    # Try first character (ICD chapter)
    first_char = icd_upper[0]
    if first_char in ICD_SEVERITY:
        return ICD_SEVERITY[first_char]
    
    return 0.0  # Unknown ICD → neutral

# ── Load Data ───────────────────────────────────────────────
print("Loading anadata from Parquet...")
ana_df = pd.read_parquet(CACHE_DIR / "acuhit2_anadata_from2025.parquet")

print(f"Loaded {len(ana_df):,} visits from {ana_df['patient_id'].nunique():,} patients")

# ── Combine Text Fields ────────────────────────────────────
# Concatenate all clinical text into one field
text_columns = ["YAKINMA", "ÖYKÜ", "Muayene Notu", "Tedavi Notu"]

def combine_text(row):
    """Combine all text fields, skip NaN."""
    texts = []
    for col in text_columns:
        if col in row and isinstance(row[col], str) and len(row[col].strip()) > 5:
            texts.append(row[col].strip())
    return " ".join(texts) if texts else ""

ana_df["clinical_text"] = ana_df.apply(combine_text, axis=1)

# ── Filter Valid Rows ──────────────────────────────────────
# Need: text (min 10 chars) + ICD code
valid = ana_df[
    (ana_df["clinical_text"].str.len() >= 10) &
    (ana_df["TANIKODU"].notna()) &
    (ana_df["TANIKODU"].astype(str).str.len() >= 3)
].copy()

print(f"Valid rows with text + ICD: {len(valid):,}")

# ── Create Labels ──────────────────────────────────────────
valid["severity_score"] = valid["TANIKODU"].astype(str).apply(get_severity_from_icd)

# Convert continuous score → 4 classes for classification
def score_to_label(score):
    if score <= -0.7:
        return "critical"
    elif score <= -0.2:
        return "moderate"
    elif score < 0.3:
        return "mild"
    else:
        return "stable"

valid["severity_label"] = valid["severity_score"].apply(score_to_label)

# ── Show Distribution ──────────────────────────────────────
print("\nSeverity distribution:")
print(valid["severity_label"].value_counts())

# ── Train/Test Split ───────────────────────────────────────
# Split by PATIENT (not by visit) to prevent data leakage
unique_patients = valid["patient_id"].unique()
train_patients, test_patients = train_test_split(
    unique_patients,
    test_size=0.2,
    random_state=42,
)

train_df = valid[valid["patient_id"].isin(train_patients)].copy()
test_df = valid[valid["patient_id"].isin(test_patients)].copy()

print(f"\nTrain: {len(train_df):,} visits from {len(train_patients):,} patients")
print(f"Test:  {len(test_df):,} visits from {len(test_patients):,} patients")

# ── Save to CSV ────────────────────────────────────────────
# Keep only needed columns
train_output = train_df[["clinical_text", "severity_label", "severity_score", "TANIKODU", "patient_id"]]
test_output = test_df[["clinical_text", "severity_label", "severity_score", "TANIKODU", "patient_id"]]

train_output.to_csv(OUTPUT_DIR / "train.csv", index=False, encoding="utf-8")
test_output.to_csv(OUTPUT_DIR / "test.csv", index=False, encoding="utf-8")

print(f"\n✅ Data saved to:")
print(f"   {OUTPUT_DIR / 'train.csv'}")
print(f"   {OUTPUT_DIR / 'test.csv'}")
print("\nNext step: Run `python scripts/train_nlp_model.py`")
