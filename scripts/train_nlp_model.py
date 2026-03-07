#!/usr/bin/env python3
"""
Fine-tune BERTurk on clinical severity classification.
No ML experience required — this script handles everything.

Training time: ~3 hours on CPU, ~30 minutes on GPU

Usage:
    python scripts/train_nlp_model.py
"""

import pandas as pd
from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    DataCollatorWithPadding,
)
from datasets import Dataset
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, classification_report
import torch

# ── Configuration ───────────────────────────────────────────
MODEL_NAME = "dbmdz/bert-base-turkish-cased"  # BERTurk
OUTPUT_DIR = Path(__file__).parent.parent / "nlp_models"
OUTPUT_DIR.mkdir(exist_ok=True)

DATA_DIR = Path(__file__).parent.parent / "nlp_data"
TRAIN_FILE = DATA_DIR / "train.csv"
TEST_FILE = DATA_DIR / "test.csv"

# Training hyperparameters (conservative, works on CPU)
BATCH_SIZE = 32       # Reduce to 16 if out of memory
NUM_EPOCHS = 3        # 3 epochs is enough
LEARNING_RATE = 2e-5  # Standard for BERT fine-tuning
MAX_LENGTH = 256      # Truncate longer texts

# ── Load Data ───────────────────────────────────────────────
print("Loading training data...")
train_df = pd.read_csv(TRAIN_FILE)
test_df = pd.read_csv(TEST_FILE)

print(f"Train: {len(train_df):,} samples")
print(f"Test:  {len(test_df):,} samples")

# ── Encode Labels ───────────────────────────────────────────
label_encoder = LabelEncoder()
train_df["label_id"] = label_encoder.fit_transform(train_df["severity_label"])
test_df["label_id"] = label_encoder.transform(test_df["severity_label"])

print(f"\nClasses: {list(label_encoder.classes_)}")
print(f"Class IDs: {list(range(len(label_encoder.classes_)))}")

# ── Convert to HuggingFace Dataset ─────────────────────────
train_dataset = Dataset.from_pandas(train_df[["clinical_text", "label_id"]])
test_dataset = Dataset.from_pandas(test_df[["clinical_text", "label_id"]])

# ── Tokenize ────────────────────────────────────────────────
print("\nLoading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

def tokenize_function(examples):
    return tokenizer(
        examples["clinical_text"],
        padding="max_length",
        truncation=True,
        max_length=MAX_LENGTH,
    )

print("Tokenizing datasets...")
train_dataset = train_dataset.map(tokenize_function, batched=True, remove_columns=["clinical_text"])
test_dataset = test_dataset.map(tokenize_function, batched=True, remove_columns=["clinical_text"])

train_dataset = train_dataset.rename_column("label_id", "labels")
test_dataset = test_dataset.rename_column("label_id", "labels")
train_dataset.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])
test_dataset.set_format(type="torch", columns=["input_ids", "attention_mask", "labels"])

# ── Load Model ──────────────────────────────────────────────
print("\nLoading BERTurk model...")
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=len(label_encoder.classes_),
    ignore_mismatched_sizes=True,
)

# ── Training Arguments ─────────────────────────────────────
training_args = TrainingArguments(
    output_dir=str(OUTPUT_DIR / "clinical_berturk"),
    num_train_epochs=NUM_EPOCHS,
    per_device_train_batch_size=BATCH_SIZE,
    per_device_eval_batch_size=BATCH_SIZE * 2,
    learning_rate=LEARNING_RATE,
    weight_decay=0.01,
    warmup_ratio=0.1,
    evaluation_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1",
    logging_steps=100,
    logging_dir=str(OUTPUT_DIR / "logs"),
    fp16=False,  # Set to True if you have GPU with CUDA
    push_to_hub=False,
)

# ── Metrics ─────────────────────────────────────────────────
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    
    accuracy = accuracy_score(labels, predictions)
    f1_macro = f1_score(labels, predictions, average="macro")
    f1_weighted = f1_score(labels, predictions, average="weighted")
    
    return {
        "accuracy": accuracy,
        "f1_macro": f1_macro,
        "f1_weighted": f1_weighted,
    }

# ── Trainer ─────────────────────────────────────────────────
data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=test_dataset,
    tokenizer=tokenizer,
    data_collator=data_collator,
    compute_metrics=compute_metrics,
)

# ── Train ───────────────────────────────────────────────────
print("\n🚀 Starting training...")
print(f"   Epochs: {NUM_EPOCHS}")
print(f"   Batch size: {BATCH_SIZE}")
print(f"   Expected time: ~3 hours on CPU, ~30 min on GPU")
print("\nTraining progress:\n")

trainer.train()

# ── Save Model ──────────────────────────────────────────────
print("\n✅ Training complete!")
print(f"Model saved to: {OUTPUT_DIR / 'clinical_berturk'}")

trainer.save_model(OUTPUT_DIR / "clinical_berturk")
tokenizer.save_pretrained(OUTPUT_DIR / "clinical_berturk")

# ── Final Evaluation ────────────────────────────────────────
print("\n" + "="*60)
print("FINAL EVALUATION ON TEST SET")
print("="*60)

predictions = trainer.predict(test_dataset)
pred_labels = np.argmax(predictions.predictions, axis=-1)

print("\nClassification Report:")
print(classification_report(
    test_dataset["labels"],
    pred_labels,
    target_names=label_encoder.classes_,
    digits=4
))

# Save label encoder for inference
import joblib
joblib.dump(label_encoder, OUTPUT_DIR / "clinical_berturk" / "label_encoder.pkl")

print(f"\n✅ Label encoder saved to: {OUTPUT_DIR / 'clinical_berturk' / 'label_encoder.pkl'}")
print("\nNext step: Run `python scripts/test_nlp_model.py` to test on sample texts")
