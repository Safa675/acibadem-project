#!/usr/bin/env python3
"""
Test the trained BERTurk model on sample clinical texts.
Compare predictions with expected severity.

Usage:
    python scripts/test_nlp_model.py
"""

from transformers import pipeline
from pathlib import Path
import joblib

# ── Load Model ──────────────────────────────────────────────
MODEL_PATH = Path(__file__).parent.parent / "nlp_models" / "clinical_berturk"

print(f"Loading model from {MODEL_PATH}...")

classifier = pipeline(
    "text-classification",
    model=str(MODEL_PATH),
    top_k=1,
)

label_encoder = joblib.load(MODEL_PATH / "label_encoder.pkl")

# ── Test Cases ──────────────────────────────────────────────
test_texts = [
    # Critical cases (should predict "critical")
    ("Göğüs ağrısı, nefes darlığı, terleme. EKG: ST elevasyonu.", "critical"),
    ("Bilinç kaybı, sağ tarafta hemipleji. BT: serebral infarktüs.", "critical"),
    ("Şiddetli göğüs ağrısı, kalp krizi şüphesi.", "critical"),
    
    # Moderate cases (should predict "moderate")
    ("Polüri, polidipsi. Kan şekeri: 320 mg/dL. Tip 2 diyabet.", "moderate"),
    ("Karın ağrısı, şişkinlik. Endoskopi: gastrik ülser.", "moderate"),
    ("Sırt ağrısı, bel fıtığı şüphesi. MR çekildi.", "moderate"),
    
    # Mild cases (should predict "mild")
    ("Hafif baş ağrısı, yorgunluk. Vital bulgular stabil.", "mild"),
    ("Öksürük, hafif ateş. Akciğer sesleri normal.", "mild"),
    ("Ciltte kaşıntı, alerjik dermatit öyküsü.", "mild"),
    
    # Stable cases (should predict "stable")
    ("Rutin kontrol. Şikayeti yok. Tüm bulgular normal.", "stable"),
    ("Sağlık taraması için geldi. Laboratuvar normal.", "stable"),
    ("İlaç kontrolü. Tansiyon regüle, şikayet yok.", "stable"),
]

# ── Run Predictions ────────────────────────────────────────
print("\n" + "="*70)
print("TEST RESULTS")
print("="*70)

correct = 0
total = len(test_texts)

for text, expected in test_texts:
    result = classifier(text)[0]
    predicted = result["label"]
    confidence = result["score"]
    
    is_correct = "✅" if predicted == expected else "❌"
    if predicted == expected:
        correct += 1
    
    print(f"\n{is_correct} Text: {text[:60]}...")
    print(f"   Expected: {expected}")
    print(f"   Predicted: {predicted} (confidence: {confidence:.2%})")

accuracy = correct / total
print(f"\n{'='*70}")
print(f"Accuracy: {correct}/{total} = {accuracy:.1%}")
print(f"{'='*70}")

if accuracy >= 0.7:
    print("✅ Model is ready for deployment!")
else:
    print("⚠️  Accuracy below 70%. Consider more training epochs or data.")
