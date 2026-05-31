"""DistilBERT 한국어 이진분류 학습 (GPU 권장, CPU 가능).

사용:
    python -m ko_pii.classifier.train \\
        --data-dir data/classifier \\
        --output-dir models/pii_classifier_v1 \\
        --model klue/roberta-small \\
        --epochs 3 --batch-size 32

Slurm:
    sbatch scripts/train_classifier.sbatch
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch
from datasets import Dataset
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f]


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    probs = torch.softmax(torch.from_numpy(logits), dim=-1)[:, 1].numpy()
    acc = accuracy_score(labels, preds)
    f1 = f1_score(labels, preds)
    p, r, _, _ = precision_recall_fscore_support(labels, preds, average="binary")
    try:
        auc = roc_auc_score(labels, probs)
    except ValueError:
        auc = float("nan")
    return {"accuracy": acc, "f1": f1, "precision": p, "recall": r, "auc": auc}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, default=Path("data/classifier"))
    ap.add_argument("--output-dir", type=Path, default=Path("models/pii_classifier_v1"))
    ap.add_argument("--model", default="klue/roberta-small")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--fp16", action="store_true", help="GPU 학습 시 권장")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    print(f"=== Loading datasets from {args.data_dir} ===")
    train_recs = load_jsonl(args.data_dir / "train.jsonl")
    val_recs = load_jsonl(args.data_dir / "val.jsonl")
    test_recs = load_jsonl(args.data_dir / "test.jsonl")
    print(f"  train={len(train_recs)} val={len(val_recs)} test={len(test_recs)}")

    train_ds = Dataset.from_list(train_recs)
    val_ds = Dataset.from_list(val_recs)
    test_ds = Dataset.from_list(test_recs)

    print(f"\n=== Loading model: {args.model} ===")
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model, num_labels=2)

    def tokenize(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=args.max_length,
            padding=False,
        )

    train_ds = train_ds.map(tokenize, batched=True, remove_columns=["text", "source"])
    val_ds = val_ds.map(tokenize, batched=True, remove_columns=["text", "source"])
    test_ds = test_ds.map(tokenize, batched=True, remove_columns=["text", "source"])

    train_ds = train_ds.rename_column("label", "labels")
    val_ds = val_ds.rename_column("label", "labels")
    test_ds = test_ds.rename_column("label", "labels")

    collator = DataCollatorWithPadding(tokenizer=tokenizer)

    print(f"\n=== Training ===")
    training_args = TrainingArguments(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size * 2,
        learning_rate=args.lr,
        warmup_ratio=0.1,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        logging_steps=50,
        save_total_limit=2,
        fp16=args.fp16,
        seed=args.seed,
        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        data_collator=collator,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    trainer.train()

    print("\n=== Eval on test set ===")
    test_metrics = trainer.evaluate(test_ds)
    print(json.dumps(test_metrics, indent=2))

    # 결과 저장
    args.output_dir.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(args.output_dir / "final"))
    tokenizer.save_pretrained(str(args.output_dir / "final"))
    with (args.output_dir / "test_metrics.json").open("w") as f:
        json.dump(test_metrics, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {args.output_dir}/final/")


if __name__ == "__main__":
    main()
